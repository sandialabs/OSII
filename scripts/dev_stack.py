#!/usr/bin/env python3
"""Run the editable OSII application stack directly on the host."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SERVICE_DISPLAY_NAMES = {
    "extractor": "Python text-layer PDF and Office extractor",
    "synthesizer": "cited source-excerpt preview (no AI)",
    "embedder": "lexical hashing vectors (no AI model)",
    "enricher": "document statistics and frequent keywords",
    "model-bridge": "Ollama/Shirty/OpenAI HTTP adapter (not Ollama itself)",
    "api": "OSII backend API and grounded chat",
    "worker": "sequential intake worker",
    "mcp": "MCP server for agents",
    "dashboard": "dashboard web interface",
}


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    working_directory: Path
    port: int


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
    provider_profile: str,
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
    tesseract_port = env.get("OSII_TESSERACT_PORT", "8080")
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
            "OSII_TESSERACT_URL": f"http://127.0.0.1:{tesseract_port}",
            "OSII_BACKEND_BASE_URL": f"http://127.0.0.1:{api_port}",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": mcp_port,
            "DEBUG": "true",
        }
    )
    env["OSII_EXTRACTOR_ROUTES_PATH"] = str(
        (REPOSITORY_ROOT / "ai-ready-ingest" / "config" / "extractor_routes_native.toml").resolve()
    )
    if provider_profile == "corporate":
        env["OSII_ENVIRONMENT"] = "corporate"
        env["OSII_EXTRACTOR_ROUTES_PATH"] = str((REPOSITORY_ROOT / "ai-ready-ingest" / "config" / "extractor_routes_corporate.toml").resolve())
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
        if provider_profile == "corporate":
            local_urls.extend([
                "http://127.0.0.1:8095/shirty/extractor",
                "http://127.0.0.1:8095/shirty/synthesizer",
            ])
        env.update({
            "OSII_PROCESSORS": ",".join(local_urls + configured),
            "OSII_DEFAULT_EXTRACTOR": "corporate.shirty-textract" if provider_profile == "corporate" else "local.native-text",
            "OSII_DEFAULT_SYNTHESIZER": "corporate.shirty-synthesis" if provider_profile == "corporate" else "ollama.synthesizer",
            "OSII_DEFAULT_EMBEDDER": "ollama.embedder",
            "OSII_DEFAULT_ENRICHER": "local.stats-keywords",
            "EMBEDDING_MODEL": ollama_embedding_model,
        })
        if provider_profile in {"baseline", "ollama"}:
            env.update({"CHAT_PROVIDER": "ollama", "CHAT_PROVIDER_CHAIN": "ollama,extractive", "OSII_SYNTHESIZER_FALLBACKS": "ollama.synthesizer,local.extractive-preview"})
        elif provider_profile == "corporate":
            env.update({"CHAT_PROVIDER": "shirty", "CHAT_PROVIDER_CHAIN": "shirty,ollama,extractive", "OSII_SYNTHESIZER_FALLBACKS": "corporate.shirty-synthesis,ollama.synthesizer,local.extractive-preview"})
    if examples and not env.get("OSII_PROCESSORS"):
        processor_port = env.get("OSII_EXAMPLE_PROCESSOR_PORT", "8091")
        env["OSII_PROCESSORS"] = f"http://127.0.0.1:{processor_port}"
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
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(**kwargs)  # type: ignore[arg-type]


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
    # Local readiness checks must never be routed through a corporate HTTP
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
    provider_profile: str,
    core_only: bool,
    dry_run: bool,
    skip_setup: bool,
) -> int:
    try:
        uv = command_path("uv")
        npm = command_path("npm")
        env = build_environment(examples, provider_profile, core_only)
        services = service_commands(uv, npm, env, core_only)

        if dry_run:
            print("[dev] Bare-metal service plan:")
            for service in services:
                print(render_command(service))
            return 0

        ensure_ports_available(services)

        if not skip_setup:
            prepare_dependencies(uv, npm, env)

        processes: dict[str, tuple[Service, subprocess.Popen[bytes]]] = {}
        dashboard_service = next(service for service in services if service.name == "dashboard")
        for service in services:
            if service.name == "dashboard":
                continue
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
            print("[dev] Python text-layer/Office extraction: http://localhost:8092/docs")
            print("[dev] Cited source-excerpt preview (no AI): http://localhost:8093/docs")
            print("[dev] Lexical hashing vectors (no AI model): http://localhost:8085/docs")
            print("[dev] Document statistics and keywords: http://localhost:8094/docs")
            print("[dev] Model HTTP adapter: http://localhost:8095/docs")
            print("[dev] OSII does not manage Ollama; Tools checks the separately configured Ollama URL.")
            print("[dev] Tesseract OCR is not started; after installing Tesseract, run make dev-ocr-host.")
            print("[dev] Apache Tika is not started; run make dev-tika in a second terminal if needed.")
            if provider_profile == "corporate":
                print("[dev] Corporate profile: Shirty is preferred when SHIRTY_BASE_URL and SHIRTY_API_KEY are set.")

        while True:
            for name, (_, process) in processes.items():
                return_code = process.poll()
                if return_code is not None:
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
    parser.add_argument("--provider-profile", choices=("baseline", "ollama", "corporate"), default="baseline")
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
        args.provider_profile,
        args.core_only,
        args.dry_run,
        args.skip_setup,
    )


if __name__ == "__main__":
    raise SystemExit(main())
