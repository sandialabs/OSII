"""Exercise the delivered executable using only a stdlib test driver on the builder."""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import closing, contextmanager
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


class Runtime:
    def __init__(self, executable: Path, directory: Path):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["OSII_BUILD_TRACE"] = "1"
        if os.name == "nt":
            environment["PATH"] = os.path.join(os.environ["SystemRoot"], "System32")
        self.process = subprocess.Popen([str(executable), "supervisor", "--data-dir", str(directory)],
            cwd=directory.parent, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")
        self.messages = queue.Queue()
        self.sequence = 0
        self.trace = deque(maxlen=400)
        def read():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
            self.messages.put({"event": "exited"})
        threading.Thread(target=read, daemon=True).start()
        def errors():
            for line in self.process.stderr:
                if len(self.trace) < 400:
                    self.trace.append(line)
        self.errors = threading.Thread(target=errors, daemon=True)
        self.errors.start()
        first = self.messages.get(timeout=30)
        if first.get("event") != "supervisor_ready":
            raise RuntimeError("The frozen supervisor did not start: " + "".join(self.trace)[-6000:])

    def request(self, command: str, **fields):
        self.sequence += 1
        self.process.stdin.write(json.dumps({"command": command, "id": self.sequence, **fields}) + "\n")
        self.process.stdin.flush()
        while True:
            value = self.messages.get(timeout=180)
            if value.get("event") == "exited":
                raise RuntimeError("Frozen supervisor exited: " + "".join(self.trace)[-6000:])
            if value.get("id") == self.sequence:
                if "error" in value:
                    raise RuntimeError(value["error"] + "\n" + "".join(self.trace)[-12000:])
                return value["result"]

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=50)
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.stdout.close()
        self.errors.join(timeout=5)
        self.process.stderr.close()


def api(session, route, payload=None, method=None):
    content = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(session["url"] + route, data=content, method=method,
        headers={"Authorization": "Bearer " + session["token"], "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{route}: {exc.code}: {exc.read().decode()[:2000]}") from exc


def wait_run(session, route, *, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = api(session, route)
        if run.get("status") in {"done", "error", "partial", "cancelled"}:
            assert run["status"] == "done", run
            return run
        time.sleep(0.2)
    raise AssertionError("Packaged worker did not finish: " + json.dumps(run))


def is_running(pid):
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def windows_processes():
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                    ("name", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = Entry()
    entry.size = ctypes.sizeof(entry)
    rows = []
    try:
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while more:
            rows.append({"pid": entry.pid, "parent": entry.parent, "name": entry.name})
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return rows


@contextmanager
def model_fixture():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value):
            content = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            self.reply({"data": [{"id": "fixture-chat"}, {"id": "fixture-embed"}]})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path.endswith("/embeddings"):
                values = payload.get("input", [])
                values = [values] if isinstance(values, str) else values
                self.reply({"model": "fixture-embed", "data": [{"index": i, "embedding": [float(len(str(text))), 1.0, 0.0]} for i, text in enumerate(values)]})
            else:
                self.reply({"model": "fixture-chat", "choices": [{"message": {"role": "assistant", "content": "The calibration result was measured twice. [1]"}, "finish_reason": "stop"}]})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_address[1]) + "/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def check(executable: Path) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="OSII frozen — ") as directory:
        temporary = Path(directory)
        source = temporary / "Documents with spaces"
        source.mkdir()
        original = source / "Résumé evidence.txt"
        original.write_text("Portable evidence survives restart. The calibration result was measured twice.", encoding="utf-8")
        original_bytes = original.read_bytes()
        application = temporary / "application"
        if os.name == "nt":
            subprocess.run([str(executable), "self-test", "--fixture-dir", str(source)], check=True, timeout=60)
        runtime = Runtime(executable, application)
        try:
            profile = runtime.request("create_profile", profile={"name": "Frozen smoke", "source": str(source)})
            session = runtime.request("open_profile", profile_id=profile["id"])
            startup_seconds = round(time.monotonic() - started, 2)
            assert api(session, "/health")["status"] == "ok"
            setup = api(session, "/api/admin/setup")
            assert setup["extraction_ready"] and not setup["ai_ready"], setup
            runtime_ports = api(session, "/api/volume/runtime")["endpoints"]
            assert all("127.0.0.1:" in endpoint for endpoint in runtime_ports.values())
            # Real isolated directory scanners must survive freezing too.
            source_id = api(session, "/api/volume/sources")["items"][0]["id"]
            scan = api(session, f"/api/volume/sources/{source_id}/scan", {})
            wait_run(session, "/api/volume/runs/" + str(scan["id"]))
            inventory = Path(profile["library"]) / "state" / "inventory.sqlite3"
            assert inventory.is_file()
            run = api(session, "/api/runs", {"queue_paths": [str(original)], "run_extraction": True,
                "synthesizer_name": "local.extractive-preview", "enricher_name": "local.stats-keywords", "build_embeddings": False})
            wait_run(session, "/api/runs/" + run.get("run_id", run["id"]))
            search = api(session, "/api/search", {"query": "calibration", "mode": "lexical"})
            assert search.get("results"), search
            collection = api(session, "/api/collections", {"name": "Preserved collection"})
            # A second supervisor cannot write the same library.
            other = Runtime(executable, application)
            try:
                try:
                    other.request("open_profile", profile_id=profile["id"])
                    raise AssertionError("Concurrent library ownership was accepted")
                except RuntimeError as exc:
                    assert "already open" in str(exc), exc
            finally:
                other.close()
            with model_fixture() as endpoint:
                api(session, "/api/admin/model-providers/frozen-fixture", {"type": "openai", "base_url": endpoint,
                    "enabled": True, "chat_model": "fixture-chat", "synthesis_model": "fixture-chat",
                    "embedding_model": "fixture-embed", "default_chat": True, "default_embedding": True}, method="PUT")
                health = api(session, "/api/admin/model-providers/frozen-fixture/health", {})
                assert health["ok"] and health["capabilities"]["embedding"]["ok"], health
                embedding = api(session, "/api/embeddings/build", {})
                wait_run(session, "/api/embeddings/build/" + embedding["run_id"])
                semantic = api(session, "/api/search", {"query": "calibration", "mode": "semantic"})
                assert semantic.get("results"), semantic
                chat = api(session, "/api/chat", {"query": "What calibration result was measured?", "scope": {"scope_type": "root"}})
                assert chat["provider"] == "openai" and chat["citations"], chat
            # A disconnected model cannot break browsing or lexical retrieval.
            assert api(session, "/api/search", {"query": "calibration", "mode": "lexical"}).get("results")
            assert original.read_bytes() == original_bytes
            pids = [row["pid"] for row in runtime.request("process_status")]
        finally:
            runtime.close()
        assert all(not is_running(pid) for pid in pids), "Closing OSII left owned helpers alive"
        # Explicitly open the same real library from a fresh application profile,
        # rather than only testing this launcher's own saved-profile reopening.
        canonical = {path: path.read_bytes() for path in Path(profile["library"]).rglob("*.toml")}
        with closing(sqlite3.connect(inventory)) as connection:
            inventory_before = connection.execute("SELECT id,path,size_bytes,mtime_ns FROM entries ORDER BY id").fetchall()
        adopted = Runtime(executable, temporary / "separate-application")
        try:
            existing = adopted.request("create_profile", profile={"name": "Existing library", "source": str(source),
                "library": profile["library"], "existing": True})
            opened = adopted.request("open_profile", profile_id=existing["id"])
            assert api(opened, "/api/search", {"query": "calibration", "mode": "lexical"}).get("results")
            assert "Preserved collection" in json.dumps(api(opened, "/api/collections"))
            assert all(path.read_bytes() == content for path, content in canonical.items())
            with closing(sqlite3.connect(inventory)) as connection:
                assert connection.execute("SELECT id,path,size_bytes,mtime_ns FROM entries ORDER BY id").fetchall() == inventory_before
        finally:
            adopted.close()
        restarted = Runtime(executable, application)
        try:
            session = restarted.request("open_profile", profile_id=profile["id"])
            assert api(session, "/api/search", {"query": "calibration", "mode": "lexical"}).get("results")
            pids = [row["pid"] for row in restarted.request("process_status")]
            if os.name == "nt":
                statuses = restarted.request("process_status")
                ocr_pid = next(row["pid"] for row in statuses if row["id"] == "ocr")
                interrupted = api(session, "/api/runs", {"queue_paths": [str(source / "interrupted-ocr.pdf")],
                    "run_extraction": True, "extractor_overrides": {".pdf": "local.tesseract-page-ocr"}})
                deadline = time.monotonic() + 25
                children = []
                while not children and time.monotonic() < deadline:
                    children = [row["pid"] for row in windows_processes() if row["parent"] == ocr_pid and row["name"].lower() == "tesseract.exe"]
                    time.sleep(0.05)
                assert children, "The interruption gate never observed a real OCR process"
                pids.extend(children)
                restarted.process.kill()
                restarted.process.wait(timeout=15)
                deadline = time.monotonic() + 10
                while any(is_running(pid) for pid in pids) and time.monotonic() < deadline:
                    time.sleep(0.1)
                assert all(not is_running(pid) for pid in pids), "Supervisor crash left helpers alive"
        finally:
            restarted.close()
        if os.name == "nt":
            recovered = Runtime(executable, application)
            try:
                session = recovered.request("open_profile", profile_id=profile["id"])
                assert api(session, "/api/search", {"query": "calibration", "mode": "lexical"}).get("results")
                api(session, "/api/runs/" + (interrupted.get("run_id") or interrupted["id"]) + "/cancel", {})
                assert original.read_bytes() == original_bytes
            finally:
                recovered.close()
    return {"status": "ok", "startup_seconds": startup_seconds,
            "checks": ["private-runtime", "metadata-scan", "intake", "baseline-processing", "lexical-search", "library-lock", "model-connection", "semantic-search", "model-chat", "endpoint-disconnect", "restart", "helper-cleanup"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.runtime.resolve())), flush=True)
