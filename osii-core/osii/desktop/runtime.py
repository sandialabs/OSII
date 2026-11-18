"""Fixed-role entry point for the frozen OSII runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def resources() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3] / "osii-desktop" / "resources"


def configure_ocr() -> None:
    root = resources() / "ocr"
    binary = root / ("tesseract.exe" if os.name == "nt" else "tesseract")
    if not binary.is_file():
        raise RuntimeError("The bundled OCR engine is missing. Reinstall OSII; no system Tesseract installation is required.")
    os.environ["OSII_TESSERACT_EXECUTABLE"] = str(binary)
    os.environ["TESSDATA_PREFIX"] = str(root / "tessdata")


def run_role(role: str) -> None:
    import base64
    import importlib
    import signal
    import socket
    import threading
    def phase(value: str):
        print(json.dumps({"osii_runtime": 1, "phase": value}), flush=True)
    phase("python_ready")
    from .windows import ProcessJob
    role_job = ProcessJob()  # A stopped OCR helper must also stop its grandchildren.
    phase("job_ready")

    # All installed roles share the same resource directory and private pipes.
    bootstrap = json.loads(sys.stdin.readline())
    phase("bootstrap_ready")
    def parent_closed():
        sys.stdin.read()
        import _thread
        _thread.interrupt_main()
    threading.Thread(target=parent_closed, daemon=True).start()
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        if getattr(sys, "frozen", False):
            raise
    phase("trust_ready")
    if role in {"worker", "inventory-worker"}:
        phase("worker_starting")
        module = "osii.worker" if role == "worker" else "osii.volume.worker"
        importlib.import_module(module).main()
        return
    if "socket_share" in bootstrap:
        sock = socket.fromshare(base64.b64decode(bootstrap["socket_share"]))
    else:
        sock = socket.socket(fileno=int(bootstrap["socket_fd"]))
    from .supervisor import SERVICES
    if role == "api":
        if os.getenv("OSII_BUILD_TRACE") == "1":
            import faulthandler
            faulthandler.dump_traceback_later(20, repeat=True)
        phase("importing_core")
        from osii.main import app
        phase("core_imported")
        if os.getenv("OSII_BUILD_TRACE") == "1":
            faulthandler.cancel_dump_traceback_later()
        from .http import attach_dashboard
        attach_dashboard(app, resources() / "dashboard", os.environ["OSII_DESKTOP_TOKEN"], port=sock.getsockname()[1])
        phase("dashboard_attached")
    else:
        app = importlib.import_module(SERVICES[role][0]).app
    import uvicorn
    phase("server_starting")
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=sock.getsockname()[1],
                                 log_level="error", access_log=False, loop="asyncio", http="h11")).run(sockets=[sock])


def main() -> int:
    from .supervisor import SERVICES
    parser = argparse.ArgumentParser(description="OSII packaged runtime")
    parser.add_argument("role", choices=["self-test", "supervisor", "api", "worker", "inventory-worker", *SERVICES])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--fixture-dir", type=Path, help="Self-test only: write a temporary OCR interruption fixture")
    args = parser.parse_args()
    configure_ocr()
    if args.fixture_dir is not None and args.role != "self-test":
        parser.error("--fixture-dir is only supported by self-test")
    if args.role == "self-test":
        from .selftest import run
        print(json.dumps(run(args.fixture_dir)), flush=True)
    elif args.role == "supervisor":
        if args.data_dir is None:
            parser.error("--data-dir is required for the supervisor")
        from .supervisor import serve
        return serve(args.data_dir)
    else:
        run_role(args.role)
    return 0
