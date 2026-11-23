"""Private Unix-socket controller for explicitly deployed OSII tool units only.

Runs on the Droplet, outside Core. No shell, arbitrary paths, environment writes,
container-engine socket, database access, or network listener.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import re
import selectors
import socketserver
import subprocess
import time

SERVICES = {
    "extractor": ("osii-extractor.service", "Document text extractor", "Reads native PDF and Office text.", "http://osii-extractor:8192"),
    "ocr-page": ("osii-ocr-page.service", "Tesseract OCR — full page", "Reads scanned pages using Tesseract.", "http://10.89.0.1:8193"),
    "ocr-regions": ("osii-ocr-regions.service", "OSII Tesseract — bounding boxes", "Extracts OCR text and document regions.", "http://10.89.0.1:8194"),
}
ACTIONS = {"start", "stop", "restart"}
SOCKET = "/run/osii-tools/control.sock"


def scrub(value: str) -> str:
    value = re.sub(r"(?im)(authorization\s*[:=]\s*)[^\n]+", r"\1[redacted]", value)
    value = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[redacted]", value)
    value = re.sub(r"(?i)((?:api[_-]?key|token|password|secret|authorization)\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]+", r"\1[redacted]", value)
    value = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", value)
    return re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", value)


def command(*args: str) -> str:
    """Bound output and runtime even if a tool writes an enormous log line."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    output = bytearray()
    deadline = time.monotonic() + 8
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while len(output) < 65536 and time.monotonic() < deadline:
                if not selector.select(timeout=max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(process.stdout.fileno(), min(4096, 65536 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
        return output.decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        process.stdout.close()


def status(service_id: str) -> dict:
    unit, name, description, url = SERVICES[service_id]
    values = dict(line.split("=", 1) for line in command(
        "/usr/bin/systemctl", "show", unit, "--property=LoadState,ActiveState,SubState,Result"
    ).splitlines() if "=" in line)
    installed = values.get("LoadState") == "loaded"
    active = values.get("ActiveState", "unknown")
    state = {"active": "running", "inactive": "stopped", "activating": "starting", "deactivating": "stopping"}.get(active, active)
    return {"id": service_id, "display_name": name, "description": description,
            "status": state if installed else "not_installed", "ownership": "osii", "url": url,
            "health_path": "/health", "can_start": installed and active in {"inactive", "failed"},
            "can_stop": installed and active in {"active", "activating"},
            "can_restart": installed and active in {"active", "failed"},
            "can_logs": installed, "detail": values.get("SubState", ""),
            "prerequisite": None if installed else "This optional service has not been deployed."}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/services":
            return self.reply(200, {"services": [status(key) for key in SERVICES]})
        parts = self.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "services" or parts[1] not in SERVICES or parts[2] != "logs":
            return self.reply(404, {"detail": "Unknown tool"})
        output = command("/usr/bin/journalctl", "--unit=" + SERVICES[parts[1]][0], "--lines=80", "--since=-1h", "--no-pager", "--output=cat")
        return self.reply(200, {"service_id": parts[1], "lines": scrub(output).splitlines()[-80:]})

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "services" or parts[1] not in SERVICES or parts[2] not in ACTIONS:
            return self.reply(404, {"detail": "Unknown tool or action"})
        if not status(parts[1])["can_logs"]:
            return self.reply(409, {"detail": "Tool is not installed"})
        try:
            subprocess.run(["/usr/bin/systemctl", "--no-block", parts[2], SERVICES[parts[1]][0]],
                           check=True, timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.SubprocessError, OSError):
            return self.reply(503, {"detail": "Service manager did not accept the action"})
        return self.reply(200, status(parts[1]))


def main():
    path = Path(SOCKET)
    path.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
