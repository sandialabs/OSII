#!/usr/bin/env python3
"""Run the editable OSII application stack directly on the host."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SERVICE_DISPLAY_NAMES = {
    "extractor": "Python text-layer PDF and Office extractor",
    "synthesizer": "cited source-excerpt preview (no AI)",
    "embedder": "lexical hashing vectors (no AI model)",
    "enricher": "document statistics and frequent keywords",
    "model-bridge": "Ollama/OpenAI-compatible HTTP adapter (not Ollama itself)",
    "api": "OSII backend API and grounded chat",
    "worker": "sequential intake worker",
    "mcp": "MCP server for agents",
    "dashboard": "dashboard web interface",
    "dataset-extractor": "CSV dataset table extractor example",
    "dataset-enricher": "dataset collection table enricher example",
}


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    working_directory: Path
    port: int
    environment: tuple[tuple[str, str], ...] = ()


CAPABILITY_SERVICE_INFO = {
    "extractor": ("Python document extractor", "Reads text-layer PDFs, Office files, and text formats.", "/health"),
    "synthesizer": ("Source excerpt preview", "Creates a cited preview without an AI model.", "/health"),
    "embedder": ("Lexical hashing compatibility embedder", "Optional lexical vectors; BM25 search works without it.", "/health"),
    "enricher": ("Statistics and keywords enricher", "Creates local document statistics and keyword artifacts.", "/health"),
    "model-bridge": ("AI provider bridge", "Connects OSII to Ollama or an OpenAI-compatible endpoint.", "/health"),
    "tika": ("Apache Tika", "Adds broad document-format text extraction using Podman or Docker.", "/version"),
}


def load_dotenv(path: Path) -> dict[str, str]:
    """Read the small KEY=VALUE subset used by OSII's checked-in example."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if value and value[0] in {"'", '"'}:
            parsed = shlex.split(value, posix=True)
            value = parsed[0] if parsed else ""
        values[key] = value
    return values


def command_path(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(
            f"Required command '{name}' was not found on PATH. "
            "The bare-metal developer workflow requires uv and Node.js/npm."
        )
    return resolved


def build_environment(
    examples: bool,
    core_only: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    for key, value in load_dotenv(REPOSITORY_ROOT / ".env").items():
        env.setdefault(key, value)

    runtime_root = REPOSITORY_ROOT / "osii-data"
    source_value = env.get("OSII_SOURCE_DIR", "./osii-data/source")
    source_root = Path(source_value)
    if not source_root.is_absolute():
        source_root = REPOSITORY_ROOT / source_root
    source_root = source_root.resolve()

    osii_root = runtime_root / ".osii"
    uploads_root = runtime_root / "uploads"
    for path in (source_root, osii_root, uploads_root):
        path.mkdir(parents=True, exist_ok=True)

    api_port = env.get("OSII_API_PORT", "8511")
    embeddings_port = env.get("OSII_EMBEDDINGS_PORT", "8085")
    tika_port = env.get("OSII_TIKA_PORT", "9998")
    mcp_port = env.get("OSII_MCP_PORT", "8022")
    workspace_python_path = os.pathsep.join(
        (
            str(REPOSITORY_ROOT / "ai-ready-ingest"),
            str(REPOSITORY_ROOT / "ai-ready-mcp"),
        )
    )
    if env.get("PYTHONPATH"):
        workspace_python_path = os.pathsep.join(
            (workspace_python_path, env["PYTHONPATH"])
        )

    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            # Pin the host workflow independently of whichever newer Python a
            # developer's package manager currently exposes by default.
            "UV_PYTHON": "3.11",
            # A visible name avoids macOS marking every .pth file beneath a
            # dot-prefixed .venv as hidden and skipping editable packages.
            "UV_PROJECT_ENVIRONMENT": str(REPOSITORY_ROOT / "osii-env"),
            # The MCP package declares `osii` as a workspace dependency. Keep
            # editable source importable even when an older uv-created .pth
            # file is present in the shared development environment.
            "PYTHONPATH": workspace_python_path,
            "SHARED_VOLUME_ROOT": str(source_root),
            "SHARED_VOLUME_HOST_PATH": str(source_root),
            "OSII_ROOT": str(osii_root),
            "UPLOAD_ORIGINALS_ROOT": str(uploads_root),
            "TIKA_URL": f"http://127.0.0.1:{tika_port}",
            "OSII_BACKEND_BASE_URL": f"http://127.0.0.1:{api_port}",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": mcp_port,
            "DEBUG": "true",
            "OSII_ENV_FILE": str((REPOSITORY_ROOT / ".env").resolve()),
            "OSII_ALLOW_LOCAL_CONFIG_WRITES": "true",
        }
    )
    env["OSII_EXTRACTOR_ROUTES_PATH"] = str(
        (REPOSITORY_ROOT / "ai-ready-ingest" / "config" / "extractor_routes_native.toml").resolve()
    )
    provider_profile = "openai" if env.get("OPENAI_BASE_URL", "").strip() else "ollama"
    if not core_only:
        ollama_embedding_model = env.get("OLLAMA_EMBEDDING_MODEL", "").strip() or "all-minilm"
        ollama_chat_model = env.get("OLLAMA_CHAT_MODEL", "").strip() or "llama3.2:1b"
        ollama_synthesis_model = env.get("OLLAMA_SYNTHESIS_MODEL", "").strip() or ollama_chat_model
        env.update({
            "OLLAMA_EMBEDDING_MODEL": ollama_embedding_model,
            "OLLAMA_SYNTHESIS_MODEL": ollama_synthesis_model,
            "OLLAMA_CHAT_MODEL": ollama_chat_model,
        })
        local_urls = [
            f"http://127.0.0.1:{env.get('OSII_LOCAL_EXTRACTOR_PORT', '8092')}",
            f"http://127.0.0.1:{env.get('OSII_LOCAL_SYNTHESIZER_PORT', '8093')}",
            f"http://127.0.0.1:{embeddings_port}",
            f"http://127.0.0.1:{env.get('OSII_LOCAL_ENRICHER_PORT', '8094')}",
            "http://127.0.0.1:8095/ollama/embedder",
            "http://127.0.0.1:8095/ollama/synthesizer",
        ]
        configured = [item for item in env.get("OSII_PROCESSORS", "").split(",") if item]
        if provider_profile == "openai":
            local_urls.extend([
                "http://127.0.0.1:8095/openai/embedder",
                "http://127.0.0.1:8095/openai/synthesizer",
            ])
        env.update({
            "OSII_PROCESSORS": ",".join(local_urls + configured),
            "OSII_DEFAULT_EXTRACTOR": "local.native-text",
            "OSII_DEFAULT_SYNTHESIZER": (
                "openai.synthesizer" if provider_profile == "openai"
                else "ollama.synthesizer"
            ),
            "OSII_DEFAULT_EMBEDDER": "openai.embedder" if provider_profile == "openai" else "ollama.embedder",
            "OSII_DEFAULT_ENRICHER": "local.stats-keywords",
            "EMBEDDING_MODEL": ollama_embedding_model,
        })
        if provider_profile in {"baseline", "ollama"}:
            env.update({"CHAT_PROVIDER": "ollama", "CHAT_PROVIDER_CHAIN": "ollama,extractive", "OSII_SYNTHESIZER_FALLBACKS": "ollama.synthesizer,local.extractive-preview"})
        elif provider_profile == "openai":
            env.update({"CHAT_PROVIDER": "openai", "CHAT_PROVIDER_CHAIN": "openai,ollama,extractive", "OSII_SYNTHESIZER_FALLBACKS": "openai.synthesizer,ollama.synthesizer,local.extractive-preview"})
    if examples:
        configured = [item for item in env.get("OSII_PROCESSORS", "").split(",") if item]
        configured.extend((
            f"http://127.0.0.1:{env.get('OSII_DATASET_EXTRACTOR_PORT', '8097')}",
            f"http://127.0.0.1:{env.get('OSII_DATASET_ENRICHER_PORT', '8098')}",
        ))
        env["OSII_PROCESSORS"] = ",".join(dict.fromkeys(configured))
    return env


def prepare_dependencies(uv: str, npm: str, env: dict[str, str]) -> None:
    print("[setup] Checking editable Python packages...")
    sync_command = [
            uv,
            "sync",
            "--package",
            "osii",
            "--package",
            "osii-mcp",
            "--package", "osii-local-extractor",
            "--package", "osii-local-synthesizer",
            "--package", "osii-local-embedder",
            "--package", "osii-local-enricher",
            "--package", "osii-model-provider-bridge",
        ]
    subprocess.run(
        sync_command,
        cwd=REPOSITORY_ROOT,
        env=env,
        check=True,
    )
    dashboard_root = REPOSITORY_ROOT / "osii-dashboard" / "dashboard"
    package_lock = dashboard_root / "package-lock.json"
    dependency_stamp = dashboard_root / "node_modules" / ".osii-package-lock.sha256"
    package_lock_hash = hashlib.sha256(package_lock.read_bytes()).hexdigest()
    installed_hash = (
        dependency_stamp.read_text(encoding="utf-8").strip()
        if dependency_stamp.exists()
        else ""
    )
    if installed_hash != package_lock_hash:
        print("[setup] Installing dashboard packages...")
        subprocess.run(
            [npm, "ci", "--no-audit", "--no-fund"],
            cwd=dashboard_root,
            env=env,
            check=True,
        )
        dependency_stamp.write_text(package_lock_hash + "\n", encoding="utf-8")
    else:
        print("[setup] Dashboard packages are current.")


def service_commands(
    uv: str,
    npm: str,
    env: dict[str, str],
    core_only: bool,
    examples: bool = False,
) -> list[Service]:
    api_port = env.get("OSII_API_PORT", "8511")
    dashboard_port = env.get("OSII_DASHBOARD_PORT", "5173")
    mcp_port = env.get("OSII_MCP_PORT", "8022")
    embeddings_port = env.get("OSII_EMBEDDINGS_PORT", "8085")

    services = [
        Service(
            "api",
            (
                uv,
                "run",
                "--package",
                "osii",
                "python",
                "-m",
                "uvicorn",
                "osii.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                api_port,
                "--reload",
                "--reload-dir",
                "osii",
            ),
            REPOSITORY_ROOT / "ai-ready-ingest",
            int(api_port),
        ),
        Service(
            "worker",
            (
                uv,
                "run",
                "--package",
                "osii",
                "python",
                "-m",
                "watchfiles",
                "--filter",
                "python",
                "python -m osii.worker",
                "osii",
            ),
            REPOSITORY_ROOT / "ai-ready-ingest",
            0,
        ),
        Service(
            "mcp",
            (
                uv,
                "run",
                "--package",
                "osii-mcp",
                "osii-mcp",
            ),
            REPOSITORY_ROOT / "ai-ready-mcp",
            int(mcp_port),
        ),
        Service(
            "dashboard",
            (
                npm,
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                dashboard_port,
            ),
            REPOSITORY_ROOT / "osii-dashboard" / "dashboard",
            int(dashboard_port),
        ),
    ]
    if not core_only:
        processors = (
            ("extractor", "osii-local-extractor", "8092", "OSII_LOCAL_EXTRACTOR_PORT", "local-extractor"),
            ("synthesizer", "osii-local-synthesizer", "8093", "OSII_LOCAL_SYNTHESIZER_PORT", "local-synthesizer"),
            ("embedder", "osii-local-embedder", "8085", "OSII_EMBEDDINGS_PORT", "local-embedder"),
            ("enricher", "osii-local-enricher", "8094", "OSII_LOCAL_ENRICHER_PORT", "local-enricher"),
        )
        for name, package, default_port, env_name, directory in reversed(processors):
            port = env.get(env_name, default_port)
            services.insert(0, Service(name, (uv, "run", "--package", package, "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port, "--reload", "--reload-dir", "app"), REPOSITORY_ROOT / "services" / directory, int(port)))
        bridge_port = env.get("OSII_MODEL_BRIDGE_PORT", "8095")
        services.insert(4, Service("model-bridge", (uv, "run", "--package", "osii-model-provider-bridge", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", bridge_port, "--reload", "--reload-dir", "app"), REPOSITORY_ROOT / "services" / "model-provider-bridge", int(bridge_port)))
    if examples:
        example_directory = REPOSITORY_ROOT / "examples" / "tabular-dataset-processors"
        dataset_extractor_port = env.get("OSII_DATASET_EXTRACTOR_PORT", "8097")
        dataset_enricher_port = env.get("OSII_DATASET_ENRICHER_PORT", "8098")
        services.insert(0, Service(
            "dataset-extractor",
            (
                uv, "run", "--package", "osii-processor-sdk", "python", "-m", "uvicorn",
                "dataset_processors:extractor_app", "--host", "127.0.0.1", "--port", dataset_extractor_port,
                "--reload", "--reload-dir", ".",
            ),
            example_directory,
            int(dataset_extractor_port),
        ))
        services.insert(1, Service(
            "dataset-enricher",
            (
                uv, "run", "--package", "osii-processor-sdk", "python", "-m", "uvicorn",
                "dataset_processors:enricher_app", "--host", "127.0.0.1", "--port", dataset_enricher_port,
                "--reload", "--reload-dir", ".",
            ),
            example_directory,
            int(dataset_enricher_port),
        ))
    return services


def ensure_ports_available(services: list[Service]) -> None:
    occupied: list[Service] = []
    for service in services:
        if service.port <= 0:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", service.port)) == 0:
                occupied.append(service)

    if occupied:
        details = ", ".join(
            f"{service.name} ({service.port})" for service in occupied
        )
        raise RuntimeError(
            f"Cannot start because these ports are already in use: {details}. "
            "Stop the previous OSII development stack, then run this command again."
        )


def render_command(service: Service) -> str:
    command = subprocess.list2cmdline(service.command)
    display_name = SERVICE_DISPLAY_NAMES.get(service.name, service.name)
    return f"[{display_name}] ({service.working_directory}) {command}"


def start_service(service: Service, env: dict[str, str]) -> subprocess.Popen[bytes]:
    display_name = SERVICE_DISPLAY_NAMES.get(service.name, service.name)
    print(f"[dev] Starting {display_name}...")
    kwargs: dict[str, object] = {
        "args": service.command,
        "cwd": service.working_directory,
        "env": {**env, **dict(service.environment)},
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(**kwargs)  # type: ignore[arg-type]


class CapabilitySupervisor:
    """Own the optional/local processing processes exposed by the Setup UI."""

    def __init__(
        self,
        *,
        services: list[Service],
        env: dict[str, str],
        uv: str,
        token: str,
    ) -> None:
        self.env = env
        self.token = token
        self.lock = threading.RLock()
        self.processes: dict[str, subprocess.Popen] = {}
        self.logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=250))
        self.services = {
            service.name: service
            for service in services
            if service.name in CAPABILITY_SERVICE_INFO
        }
        self.tika_port = int(env.get("OSII_TIKA_PORT", "9998"))
        self.server: ThreadingHTTPServer | None = None

    def _reachable(self, service_id: str) -> bool:
        port = self.tika_port if service_id == "tika" else self.services[service_id].port
        if port <= 0:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.15)
            return probe.connect_ex(("127.0.0.1", port)) == 0

    def _capture_output(self, service_id: str, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for raw in iter(process.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self.logs[service_id].append(line)
                print(f"[{service_id}] {line}")

    def _start_process(self, service_id: str) -> None:
        service = self.services[service_id]
        if self._reachable(service_id):
            raise RuntimeError(f"{CAPABILITY_SERVICE_INFO[service_id][0]} is already running externally.")
        kwargs: dict[str, object] = {
            "args": service.command,
            "cwd": service.working_directory,
            "env": {**self.env, **dict(service.environment)},
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(**kwargs)  # type: ignore[arg-type]
        self.processes[service_id] = process
        threading.Thread(
            target=self._capture_output,
            args=(service_id, process),
            daemon=True,
        ).start()

    def start_initial(self, service: Service) -> subprocess.Popen:
        with self.lock:
            self._start_process(service.name)
            return self.processes[service.name]

    def _compose_command(self) -> list[str] | None:
        configured = self.env.get("OSII_COMPOSE_COMMAND", "").strip()
        if configured:
            return shlex.split(configured, posix=os.name != "nt")
        if shutil.which("podman-compose"):
            return ["podman-compose"]
        if shutil.which("docker"):
            return ["docker", "compose"]
        return None

    def _compose(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        command = self._compose_command()
        if command is None:
            raise RuntimeError("Podman Compose or Docker Compose is required to start Apache Tika.")
        return subprocess.run(
            [*command, "--profile", "ocr", *arguments],
            cwd=REPOSITORY_ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )

    def status(self, service_id: str) -> dict[str, object]:
        if service_id not in {*self.services, "tika"}:
            raise KeyError(service_id)
        with self.lock:
            process = self.processes.get(service_id)
            owned_running = process is not None and process.poll() is None
            reachable = self._reachable(service_id)
            if owned_running:
                state, ownership = "running", "osii"
            elif reachable:
                state, ownership = "external", "external"
            elif process is not None and process.returncode not in (None, 0):
                state, ownership = "failed", "osii"
            else:
                state, ownership = "stopped", "none"
            title, description, health_path = CAPABILITY_SERVICE_INFO[service_id]
            port = self.tika_port if service_id == "tika" else self.services[service_id].port
            prerequisite = None
            if service_id == "tika" and self._compose_command() is None:
                prerequisite = "Install Podman Compose or Docker Compose to run Apache Tika."
            return {
                "id": service_id,
                "display_name": title,
                "description": description,
                "status": state,
                "ownership": ownership,
                "url": f"http://127.0.0.1:{port}",
                "health_path": health_path,
                "can_start": state in {"stopped", "failed"} and prerequisite is None,
                "can_stop": owned_running,
                "can_restart": owned_running,
                "prerequisite": prerequisite,
                "detail": self.logs[service_id][-1] if self.logs[service_id] else None,
            }

    def list_status(self) -> list[dict[str, object]]:
        return [self.status(item) for item in (*self.services.keys(), "tika")]

    def action(self, service_id: str, action: str) -> dict[str, object]:
        if service_id not in {*self.services, "tika"}:
            raise KeyError(service_id)
        if action not in {"start", "stop", "restart"}:
            raise ValueError("Unsupported service action")
        with self.lock:
            if action in {"stop", "restart"}:
                if service_id == "tika":
                    result = self._compose("stop", "tika")
                    if result.returncode != 0:
                        raise RuntimeError((result.stderr or result.stdout).strip())
                else:
                    process = self.processes.get(service_id)
                    if process is None or process.poll() is not None:
                        raise RuntimeError("OSII does not own this service process.")
                    stop_service(process)
                    self.processes.pop(service_id, None)
            if action in {"start", "restart"}:
                if service_id == "tika":
                    result = self._compose("up", "-d", "tika")
                    self.logs[service_id].extend(
                        line for line in (result.stdout + result.stderr).splitlines() if line
                    )
                    if result.returncode != 0:
                        raise RuntimeError((result.stderr or result.stdout).strip())
                else:
                    self._start_process(service_id)
            return self.status(service_id)

    def service_logs(self, service_id: str) -> list[str]:
        if service_id not in {*self.services, "tika"}:
            raise KeyError(service_id)
        if service_id == "tika" and self._compose_command() is not None:
            result = self._compose("logs", "--tail", "200", "tika")
            if result.stdout:
                self.logs[service_id].extend(result.stdout.splitlines())
        return list(self.logs[service_id])

    def start_http(self, port: int) -> None:
        supervisor = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, status: int, payload: object) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                return self.headers.get("Authorization") == f"Bearer {supervisor.token}"

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._json(403, {"detail": "Forbidden"})
                    return
                parts = self.path.strip("/").split("/")
                try:
                    if self.path == "/services":
                        self._json(200, {"services": supervisor.list_status()})
                    elif len(parts) == 3 and parts[0] == "services" and parts[2] == "logs":
                        self._json(200, {"service_id": parts[1], "lines": supervisor.service_logs(parts[1])})
                    else:
                        self._json(404, {"detail": "Not found"})
                except KeyError:
                    self._json(404, {"detail": "Unknown service"})

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._json(403, {"detail": "Forbidden"})
                    return
                parts = self.path.strip("/").split("/")
                try:
                    if len(parts) == 3 and parts[0] == "services":
                        self._json(200, supervisor.action(parts[1], parts[2]))
                    else:
                        self._json(404, {"detail": "Not found"})
                except KeyError:
                    self._json(404, {"detail": "Unknown service"})
                except (RuntimeError, ValueError) as exc:
                    self._json(409, {"detail": str(exc)})

            def log_message(self, *_: object) -> None:
                return

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot start the local capability supervisor on port {port}: {exc}"
            ) from exc
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        with self.lock:
            for process in reversed(list(self.processes.values())):
                stop_service(process)
            self.processes.clear()


def stop_service(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # uvicorn --reload, watchfiles, and npm/Vite all create child
        # processes. Stopping only the uv/npm parent leaves those children
        # listening on their ports on Windows. taskkill /T tears down the
        # complete tree; /F is equivalent to the existing kill fallback and
        # is necessary for reloaders that do not handle CTRL_BREAK reliably.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def wait_for_http_service(
    *,
    service_name: str,
    url: str,
    processes: dict[str, tuple[Service, subprocess.Popen[bytes]]],
    timeout_seconds: float = 90.0,
) -> None:
    """Wait for a required service without letting the UI race its startup."""
    deadline = time.monotonic() + timeout_seconds
    # Local readiness checks must never be routed through an external HTTP
    # proxy, even when proxy environment variables are present.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    print(f"[dev] Waiting for {service_name}: {url}")

    while time.monotonic() < deadline:
        for name, (_, process) in processes.items():
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(
                    f"{name} exited with code {return_code} while waiting for "
                    f"{service_name}. Review that service's error above."
                )

        try:
            with opener.open(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    print(f"[dev] {service_name} is ready.")
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)

    raise RuntimeError(
        f"{service_name} did not become ready within {timeout_seconds:.0f} seconds at {url}. "
        "Review the API startup output above; the dashboard was not started."
    )


def run(
    examples: bool,
    core_only: bool,
    dry_run: bool,
    skip_setup: bool,
) -> int:
    try:
        uv = command_path("uv")
        npm = command_path("npm")
        env = build_environment(examples, core_only)
        provider_profile = "openai" if env.get("OPENAI_BASE_URL", "").strip() else "ollama"
        services = service_commands(uv, npm, env, core_only, examples)

        supervisor: CapabilitySupervisor | None = None
        if not core_only:
            supervisor_token = secrets.token_urlsafe(32)
            supervisor_port = int(env.get("OSII_SERVICE_SUPERVISOR_PORT", "8510"))
            env.update(
                {
                    "OSII_SERVICE_SUPERVISOR_URL": f"http://127.0.0.1:{supervisor_port}",
                    "OSII_SERVICE_SUPERVISOR_TOKEN": supervisor_token,
                }
            )
            supervisor = CapabilitySupervisor(
                services=services,
                env=env,
                uv=uv,
                token=supervisor_token,
            )

        if dry_run:
            print("[dev] Bare-metal service plan:")
            for service in services:
                print(render_command(service))
            return 0

        ensure_ports_available(services)

        if not skip_setup:
            prepare_dependencies(uv, npm, env)

        processes: dict[str, tuple[Service, subprocess.Popen[bytes]]] = {}
        if supervisor is not None:
            supervisor.start_http(int(env.get("OSII_SERVICE_SUPERVISOR_PORT", "8510")))
        dashboard_service = next(service for service in services if service.name == "dashboard")
        for service in services:
            if service.name == "dashboard":
                continue
            if supervisor is not None and service.name in CAPABILITY_SERVICE_INFO:
                processes[service.name] = (service, supervisor.start_initial(service))
            else:
                processes[service.name] = (service, start_service(service, env))
        dashboard_port = env.get("OSII_DASHBOARD_PORT", "5173")
        api_port = env.get("OSII_API_PORT", "8511")
        wait_for_http_service(
            service_name="OSII backend API",
            url=f"http://127.0.0.1:{api_port}/health",
            processes=processes,
        )
        processes[dashboard_service.name] = (
            dashboard_service,
            start_service(dashboard_service, env),
        )
        print()
        print(f"[dev] Dashboard: http://localhost:{dashboard_port}")
        print(f"[dev] API health: http://localhost:{api_port}/health")
        print(f"[dev] MCP: http://localhost:{env.get('OSII_MCP_PORT', '8022')}/mcp")
        print("[dev] Press Ctrl+C to stop host processes.")
        if not core_only:
            print("[dev] Open Dashboard → Setup to connect AI or start optional Tika/Tesseract capabilities.")
            print("[dev] Setup → Advanced & diagnostics contains processor URLs, settings, controls, and logs.")
            if provider_profile == "openai":
                print("[dev] OpenAI-compatible profile: the configured endpoint is preferred, with Ollama and extractive fallbacks.")

        while True:
            for name, (_, process) in processes.items():
                return_code = process.poll()
                if return_code is not None:
                    if name in CAPABILITY_SERVICE_INFO:
                        continue
                    raise RuntimeError(
                        f"{name} exited unexpectedly with code {return_code}"
                    )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[dev] Stopping host processes...")
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[dev] {exc}", file=sys.stderr)
        return 1
    finally:
        if "supervisor" in locals() and supervisor is not None:
            supervisor.close()
        if "processes" in locals():
            for _, process in reversed(list(processes.values())):
                stop_service(process)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run editable OSII services on the host."
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Connect the example processor at its localhost port.",
    )
    parser.add_argument("--core-only", action="store_true", help="Start app services without local processors.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the host service plan without installing or starting anything.",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip Python and dashboard dependency checks.",
    )
    args = parser.parse_args()
    return run(
        args.examples,
        args.core_only,
        args.dry_run,
        args.skip_setup,
    )


if __name__ == "__main__":
    raise SystemExit(main())
