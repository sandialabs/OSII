#!/usr/bin/env python3
"""Run the editable OSII application stack on the host.

Podman supplies only the system-level OCR dependencies in development. This
launcher supervises the Python services and Vite so source changes are visible
without rebuilding deployment images.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    working_directory: Path


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


def build_environment(examples: bool) -> dict[str, str]:
    env = os.environ.copy()
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
    model_root = runtime_root / "models"
    for path in (source_root, osii_root, uploads_root, model_root):
        path.mkdir(parents=True, exist_ok=True)

    api_port = env.get("OSII_API_PORT", "8511")
    embeddings_port = env.get("OSII_EMBEDDINGS_PORT", "8085")
    tesseract_port = env.get("OSII_TESSERACT_PORT", "8080")
    tika_port = env.get("OSII_TIKA_PORT", "9998")

    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "SHARED_VOLUME_ROOT": str(source_root),
            "SHARED_VOLUME_HOST_PATH": str(source_root),
            "OSII_ROOT": str(osii_root),
            "UPLOAD_ORIGINALS_ROOT": str(uploads_root),
            "TIKA_URL": f"http://127.0.0.1:{tika_port}",
            "OSII_TESSERACT_URL": f"http://127.0.0.1:{tesseract_port}",
            "OSII_EMBEDDING_BASE_URL": f"http://127.0.0.1:{embeddings_port}/v1",
            "OSII_BACKEND_BASE_URL": f"http://127.0.0.1:{api_port}",
            "MODEL_NAME": env.get(
                "MODEL_NAME",
                env.get(
                    "EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-en"
                ),
            ),
            "HF_HOME": str(model_root / "huggingface"),
            "TRANSFORMERS_CACHE": str(model_root / "huggingface"),
            "SENTENCE_TRANSFORMERS_HOME": str(model_root / "sentence-transformers"),
        }
    )
    if examples and not env.get("OSII_PROCESSORS"):
        processor_port = env.get("OSII_EXAMPLE_PROCESSOR_PORT", "8091")
        env["OSII_PROCESSORS"] = f"http://127.0.0.1:{processor_port}"
    return env


def prepare_dependencies(uv: str, npm: str, env: dict[str, str]) -> None:
    print("[setup] Checking editable Python packages...")
    subprocess.run(
        [
            uv,
            "sync",
            "--package",
            "osii",
            "--package",
            "ai-ready-chat",
        ],
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


def service_commands(uv: str, npm: str, env: dict[str, str]) -> list[Service]:
    api_port = env.get("OSII_API_PORT", "8511")
    chat_port = env.get("OSII_CHAT_PORT", "8611")
    dashboard_port = env.get("OSII_DASHBOARD_PORT", "5173")
    embeddings_port = env.get("OSII_EMBEDDINGS_PORT", "8085")
    embedding_root = (
        REPOSITORY_ROOT / "ai-ready-tool-shelf" / "embedding-service-jina"
    )

    return [
        Service(
            "embeddings",
            (
                uv,
                "run",
                "--no-project",
                "--python",
                "3.11",
                "--with-requirements",
                str(embedding_root / "requirements.txt"),
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                embeddings_port,
            ),
            embedding_root,
        ),
        Service(
            "api",
            (
                uv,
                "run",
                "--package",
                "osii",
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
        ),
        Service(
            "worker",
            (
                uv,
                "run",
                "--package",
                "osii",
                "watchfiles",
                "--filter",
                "python",
                "python -m osii.worker",
                "osii",
            ),
            REPOSITORY_ROOT / "ai-ready-ingest",
        ),
        Service(
            "chat",
            (
                uv,
                "run",
                "--package",
                "ai-ready-chat",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                chat_port,
                "--reload",
                "--reload-dir",
                "app",
            ),
            REPOSITORY_ROOT / "ai-ready-rag-chat",
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
        ),
    ]


def render_command(service: Service) -> str:
    command = subprocess.list2cmdline(service.command)
    return f"[{service.name}] ({service.working_directory}) {command}"


def start_service(service: Service, env: dict[str, str]) -> subprocess.Popen[bytes]:
    print(f"[dev] Starting {service.name}...")
    kwargs: dict[str, object] = {
        "args": service.command,
        "cwd": service.working_directory,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(**kwargs)  # type: ignore[arg-type]


def stop_service(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def run(examples: bool, dry_run: bool, skip_setup: bool) -> int:
    try:
        uv = command_path("uv")
        npm = command_path("npm")
        env = build_environment(examples)
        services = service_commands(uv, npm, env)

        if dry_run:
            print("[dev] Bare-metal service plan:")
            for service in services:
                print(render_command(service))
            return 0

        if not skip_setup:
            prepare_dependencies(uv, npm, env)

        processes: dict[str, tuple[Service, subprocess.Popen[bytes]]] = {}
        for service in services:
            processes[service.name] = (service, start_service(service, env))
        dashboard_port = env.get("OSII_DASHBOARD_PORT", "5173")
        api_port = env.get("OSII_API_PORT", "8511")
        print()
        print(f"[dev] Dashboard: http://localhost:{dashboard_port}")
        print(f"[dev] API health: http://localhost:{api_port}/health")
        print("[dev] Press Ctrl+C to stop host processes.")
        print("[dev] The first embedding start downloads the model; later starts reuse it.")

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
    return run(args.examples, args.dry_run, args.skip_setup)


if __name__ == "__main__":
    raise SystemExit(main())
