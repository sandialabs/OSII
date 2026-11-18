"""Own the packaged process tree; private JSON-lines control over inherited pipes."""
from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from osii.library_lock import LibraryLock
from .profiles import Profiles, check_library, require_local, validate_source
from .windows import ProcessJob

SERVICES = {
    "extractor": ("osii_local_extractor.main", "Python document extractor"),
    "ocr": ("osii_local_tesseract.main", "Bundled Tesseract OCR"),
    "synthesizer": ("osii_local_synthesizer.main", "Source excerpt preview — no AI"),
    "embedder": ("osii_local_embedder.main", "Lexical hashing — no AI"),
    "enricher": ("osii_local_enricher.main", "Statistics and keywords"),
    "model-bridge": ("osii_model_provider_bridge.main", "Optional AI provider connection"),
}


def listener(port: int = 0) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return sock
    except BaseException:
        sock.close()
        raise


def command(role: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, role]
    return [sys.executable, str(Path(__file__).resolve().parents[3] / "scripts" / "standalone_runtime.py"), role]


@dataclass
class Service:
    id: str
    port: int = 0
    process: subprocess.Popen | None = None
    stopped: bool = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Supervisor:
    def __init__(self, directory: Path):
        self.job = ProcessJob()  # Assign BEFORE spawning, including OCR grandchildren.
        self.profiles = Profiles(directory)
        self.stopping = threading.Event()
        self.guard = threading.RLock()
        self.services: dict[str, Service] = {}
        self.events: dict[str, deque] = {}
        self.library_lock: LibraryLock | None = None
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.profile: dict | None = None
        self.environment: dict[str, str] = {}
        self.token = ""
        logs = self.profiles.directory / "logs"
        logs.mkdir(exist_ok=True)
        self.log = logging.getLogger("osii.desktop.lifecycle." + str(id(self)))
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        self.handler = RotatingFileHandler(logs / "lifecycle.jsonl", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        self.log.addHandler(self.handler)

    def record(self, service: str, event: str, *, exit_code: int | None = None) -> None:
        # Only fixed lifecycle fields enter exported diagnostics. Child stdout,
        # document text, model responses, paths and credentials never enter it.
        row = {"time": datetime.now(timezone.utc).isoformat(), "service": service, "event": event}
        if exit_code is not None:
            row["exit_code"] = exit_code
        self.log.info(json.dumps(row))
        self.events.setdefault(service, deque(maxlen=100)).append(row)

    def environment_for(self, profile: dict, ports: dict[str, int]) -> dict[str, str]:
        # Never inherit deployment flags, provider credentials or PYTHONPATH
        # from a source checkout. Proxy/certificate settings remain explicit OS
        # integration options; Windows system trust is enabled in each child.
        kept = {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "USERPROFILE",
                "HOME", "LANG", "LC_ALL", "PATH", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}
        env = {key: value for key, value in os.environ.items() if key.upper() in {name.upper() for name in kept}}
        if not getattr(sys, "frozen", False):
            # Source-only diagnostic execution; installed builds never need this.
            core = Path(__file__).resolve().parents[2]
            env["PYTHONPATH"] = str(core) + os.pathsep + os.pathsep.join(str(core / "services" / name) for name in
                ("local-extractor", "local-tesseract", "local-synthesizer", "local-embedder", "local-enricher", "model-provider-bridge"))
        runtime = self.profiles.directory / "profiles" / profile["id"]
        modules = runtime / "modules"
        modules.mkdir(exist_ok=True)
        bridge = f"http://127.0.0.1:{ports['model-bridge']}"
        processors = [f"http://127.0.0.1:{ports[name]}" for name in SERVICES if name != "model-bridge"]
        processors += [bridge + f"/{provider}/{kind}" for provider in ("ollama", "openai") for kind in ("embedder", "synthesizer")]
        env.update({
            "PYTHONUNBUFFERED": "1", "OSII_STANDALONE": "1", "OSII_STORAGE_BACKEND": "sidecar",
            "OSII_RUNTIME_DIR": str(runtime), "OSII_ROOT": profile["library"], "OSII_CONFIG_DIR": profile["config"],
            "OSII_ENV_FILE": str(Path(profile["config"]) / "secrets.env"), "OSII_ACTIVE_PROFILE": profile["id"],
            "OSII_ALLOW_LOCAL_CONFIG_WRITES": "true", "OSII_PROCESSOR_MODULES_DIR": str(modules),
            "SHARED_VOLUME_ROOT": profile["source"], "SHARED_VOLUME_HOST_PATH": profile["source"],
            "OSII_SOURCE_DIR": profile["source"], "OSII_FILESYSTEM_MODE": "local", "OSII_SOURCE_KIND": "auto",
            "OSII_INVENTORY_DB": str(Path(profile["library"]) / "state" / "inventory.sqlite3"),
            "UPLOAD_ORIGINALS_ROOT": str(runtime / "uploads"), "OSII_PROCESSORS": ",".join(processors),
            "OSII_DEFAULT_EXTRACTOR": "local.native-text", "OSII_DEFAULT_ENRICHER": "local.stats-keywords",
            "OSII_INTAKE_PRESET": "text",
            "OSII_MODEL_BRIDGE_URL": bridge, "OSII_MODEL_GATEWAY_PUBLIC_URL": bridge + "/v1",
            "OSII_MODEL_GATEWAY_SECRET": secrets.token_urlsafe(48), "OSII_DESKTOP_TOKEN": self.token,
            "OSII_NATIVE_EXTRACTOR_URL": f"http://127.0.0.1:{ports['extractor']}",
            "OSII_OCR_URL": f"http://127.0.0.1:{ports['ocr']}",
            "OSII_PREVIEW_URL": f"http://127.0.0.1:{ports['synthesizer']}",
            "OSII_ENRICHER_URL": f"http://127.0.0.1:{ports['enricher']}",
        })
        return env

    def spawn(self, service: Service, sock: socket.socket | None = None) -> None:
        options = {"env": self.environment, "cwd": str(self.profiles.directory), "stdin": subprocess.PIPE,
                   "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            options["start_new_session"] = True
            if sock is not None:
                options["pass_fds"] = (sock.fileno(),)
        try:
            process = subprocess.Popen(command(service.id), **options)
            service.process = process
            service.stopped = False
            bootstrap = {}
            if sock is not None:
                bootstrap = ({"socket_share": base64.b64encode(sock.share(process.pid)).decode()}
                             if os.name == "nt" else {"socket_fd": sock.fileno()})
            assert process.stdin
            process.stdin.write((json.dumps(bootstrap) + "\n").encode())
            process.stdin.flush()
            self.record(service.id, "started")
        finally:
            if sock is not None:
                sock.close()

    def wait_ready(self, service: Service, timeout: float = 90) -> None:
        deadline = time.monotonic() + timeout
        headers = {"Authorization": "Bearer " + self.token} if service.id == "api" else {}
        path = "/ready" if service.id == "ocr" else "/health"
        request = urllib.request.Request(service.url + path, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if self.stopping.is_set():
                raise RuntimeError("Startup cancelled")
            if service.process is None or service.process.poll() is not None:
                code = service.process.returncode if service.process else -1
                self.record(service.id, "startup_failed", exit_code=code)
                raise RuntimeError(f"The bundled {service.id} process stopped during startup (exit {code}). Reinstall OSII or export diagnostics.")
            try:
                with opener.open(request, timeout=1) as response:
                    if response.status == 200:
                        self.record(service.id, "ready")
                        return
            except OSError:
                pass
            self.stopping.wait(0.15)
        self.record(service.id, "startup_timeout")
        raise RuntimeError(f"The bundled {service.id} process did not become ready within {int(timeout)} seconds.")

    def start(self, identifier: str) -> dict:
        if self.profile:
            raise ValueError("Close the current library before opening another.")
        profile = self.profiles.get(identifier)
        root, source = Path(profile["library"]), Path(profile["source"])
        require_local(root)
        validate_source(source, root)
        self.library_lock = LibraryLock(root).acquire()
        reserved: dict[str, socket.socket] = {}
        try:
            check_library(root, existing=True)
            for name in (*SERVICES, "api", "control"):
                reserved[name] = listener()
            ports = {name: sock.getsockname()[1] for name, sock in reserved.items()}
            self.token = secrets.token_urlsafe(48)
            self.environment = self.environment_for(profile, ports)
            self.environment.update(OSII_SERVICE_SUPERVISOR_URL=f"http://127.0.0.1:{ports['control']}",
                                    OSII_SERVICE_SUPERVISOR_TOKEN=secrets.token_urlsafe(48))
            self.profile = profile
            for name in (*SERVICES, "api"):
                service = self.services[name] = Service(name, ports[name])
                self.spawn(service, reserved.pop(name))
            self.start_control(reserved.pop("control"))
            for name in (*SERVICES, "api"):
                self.wait_ready(self.services[name])
            for name in ("worker", "inventory-worker"):
                service = self.services[name] = Service(name)
                self.spawn(service)
            self.stopping.wait(0.25)
            self.check_processes()
            return {"url": self.services["api"].url, "token": self.token, "profile": profile}
        except BaseException:
            self.close_library()
            raise
        finally:
            for sock in reserved.values():
                sock.close()

    def stop(self, service: Service) -> None:
        service.stopped = True
        process = service.process
        if process is None or process.poll() is not None:
            return
        if process.stdin:
            process.stdin.close()  # Child's pipe watcher raises SIGINT.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
        self.record(service.id, "stopped", exit_code=process.returncode)

    def statuses(self) -> list[dict]:
        rows = []
        for name, (_, title) in SERVICES.items():
            service = self.services.get(name)
            if service is None:
                continue
            running = service.process is not None and service.process.poll() is None
            rows.append({"id": name, "display_name": title, "description": "Bundled with OSII; no separate installation required.",
                         "status": "running" if running else "stopped" if service.stopped else "failed", "ownership": "osii",
                         "url": service.url, "health_path": "/health", "can_start": not running, "can_stop": running,
                         "can_restart": running, "prerequisite": None, "detail": None})
        return rows

    def start_control(self, sock: socket.socket) -> None:
        supervisor = self
        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + supervisor.environment["OSII_SERVICE_SUPERVISOR_TOKEN"]):
                    return self.reply(403, {"detail": "Private OSII service"})
                parts = self.path.strip("/").split("/")
                with supervisor.guard:
                    if self.command == "GET" and parts == ["services"]:
                        return self.reply(200, {"services": supervisor.statuses()})
                    if len(parts) == 3 and parts[0] == "services" and parts[1] in SERVICES:
                        name, action = parts[1:]
                        if self.command == "GET" and action == "logs":
                            return self.reply(200, {"service_id": name, "lines": [json.dumps(row) for row in supervisor.events.get(name, [])]})
                        if self.command == "POST" and action in {"start", "stop", "restart"}:
                            service = supervisor.services[name]
                            try:
                                running = service.process and service.process.poll() is None
                                if action == "stop" or action == "restart":
                                    supervisor.stop(service)
                                if action == "restart" or (action == "start" and not running):
                                    supervisor.spawn(service, listener(service.port))
                                    supervisor.wait_ready(service)
                                return self.reply(200, {"services": supervisor.statuses()})
                            except (RuntimeError, OSError) as exc:
                                return self.reply(503, {"detail": str(exc)})
                    self.reply(404, {"detail": "Unknown bundled service action"})

            def reply(self, status, payload):
                content = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            do_GET = handle_request
            do_POST = handle_request

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(sock.getsockname(), Handler, bind_and_activate=False)
        self.server.server_close()
        self.server.socket = sock
        self.server.server_activate()
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def check_processes(self) -> None:
        for name, service in self.services.items():
            process = service.process
            if process and not service.stopped and process.poll() is not None:
                self.record(name, "unexpected_exit", exit_code=process.returncode)
                service.stopped = True
                if name in {"api", "worker", "inventory-worker"}:
                    raise RuntimeError(f"OSII's {name} stopped unexpectedly. Close the library and reopen it to recover queued work.")

    def close_library(self) -> None:
        # Management requests must finish before releasing library ownership.
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.server_thread:
            self.server_thread.join(timeout=5)
            self.server_thread = None
        with self.guard:
            for service in reversed(list(self.services.values())):
                self.stop(service)
            self.services.clear()
            self.profile = None
            if self.library_lock:
                self.library_lock.close()
                self.library_lock = None

    def close(self) -> None:
        self.close_library()
        self.handler.close()
        self.log.removeHandler(self.handler)


def serve(directory: Path) -> int:
    supervisor = Supervisor(directory)
    incoming = queue.Queue()
    def read_commands():
        try:
            while line := sys.stdin.readline(65537):
                if len(line) > 65536:
                    break
                try:
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        break
                    if payload.get("command") == "shutdown":
                        supervisor.stopping.set()
                    incoming.put(payload)
                except ValueError:
                    break
        finally:
            supervisor.stopping.set()
    threading.Thread(target=read_commands, daemon=True).start()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: supervisor.stopping.set())
    print(json.dumps({"event": "supervisor_ready", "protocol": 1}), flush=True)
    try:
        while not supervisor.stopping.is_set():
            try:
                payload = incoming.get(timeout=0.25)
            except queue.Empty:
                try:
                    supervisor.check_processes()
                except RuntimeError as exc:
                    print(json.dumps({"event": "runtime_failed", "error": str(exc)}), flush=True)
                    supervisor.close_library()
                continue
            result = {"id": payload.get("id")}
            try:
                action = payload.get("command")
                if action == "profiles":
                    result["result"] = supervisor.profiles.list()
                elif action == "create_profile":
                    fields = payload.get("profile", {})
                    if not isinstance(fields, dict) or set(fields) - {"source", "name", "library", "config", "existing"}:
                        raise ValueError("Invalid library selection")
                    result["result"] = supervisor.profiles.create(**fields)
                elif action == "open_profile":
                    result["result"] = supervisor.start(str(payload.get("profile_id", "")))
                elif action == "close_library":
                    supervisor.close_library()
                    result["result"] = {"closed": True}
                elif action == "process_status":
                    result["result"] = [{"id": name, "pid": service.process.pid,
                                          "running": service.process.poll() is None}
                                         for name, service in supervisor.services.items() if service.process]
                else:
                    raise ValueError("Unknown desktop operation")
            except (ValueError, RuntimeError, OSError, TypeError) as exc:
                result["error"] = str(exc)
                supervisor.record("supervisor", "operation_failed")
            print(json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        supervisor.close()
    return 0
