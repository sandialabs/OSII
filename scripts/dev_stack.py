"""Run OSII-server locally; database migration/bootstrap remain explicit."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "osii-core"))
from osii.processor_modules import active_processors, modules_directory, enabled, ModuleManifestError


def processor_modules(env: dict[str, str]):
    """Server development opts in; hosted API never launches filesystem modules."""
    if not enabled(env.get("OSII_START_PROCESSOR_MODULES", env.get("OSII_START_TOOLBOX", "false"))):
        return []
    return active_processors(modules_directory(env, ROOT), env)


def module_command(processor, uv: str, env: dict[str, str]) -> list[str]:
    return [uv, "run", "--python", "3.12", "--project", ".",
        *[arg for extra in processor.extras for arg in ("--extra", extra)],
        "python", *processor.command, "--host", "127.0.0.1", "--port", str(processor.resolved_port(env))]



def service_environment(name: str, env: dict[str, str], modules) -> dict[str, str]:
    result = dict(env)
    if name not in {"API", "Worker"}:
        result.pop("DATABASE_URL", None)
        result.pop("OSII_STORAGE_BACKEND", None)
    processor = next((row for row in modules if row.id == name), None)
    if processor:
        result["UV_PROJECT_ENVIRONMENT"] = str(processor.directory / "osii-env")
    return result


def load_dotenv(path: Path) -> dict[str, str]:
    result = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                value = value.strip()
                result[key.strip()] = value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value.split(" #", 1)[0].strip()
    return result


def ensure_postgres(env: dict[str, str], *, dry_run: bool = False) -> None:
    """Start only an explicitly configured, already initialized local cluster."""
    directory = env.get("OSII_DEV_POSTGRES_DIR", "")
    if not directory:
        if dry_run:
            print("PostgreSQL: externally managed (no local cluster configured)")
        return
    data = Path(directory).expanduser()
    data = (data if data.is_absolute() else ROOT / data).resolve()
    try:
        url = urlsplit(env["DATABASE_URL"])
        host, port = url.hostname, url.port or 5432
    except ValueError:
        raise RuntimeError("DATABASE_URL is invalid; check its host and port") from None
    if url.scheme not in {"postgresql", "postgresql+psycopg"} or host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("OSII_DEV_POSTGRES_DIR requires a loopback PostgreSQL DATABASE_URL; unset it for an externally managed database")
    version_file = data / "PG_VERSION"
    if not version_file.is_file():
        raise RuntimeError(f"No initialized PostgreSQL cluster at {data}. Configure an existing cluster; make dev does not create databases.")
    major = version_file.read_text().strip()
    executable = "pg_ctl.exe" if os.name == "nt" else "pg_ctl"
    configured_bin = env.get("OSII_DEV_POSTGRES_BIN", "")
    if configured_bin:
        binary = Path(configured_bin).expanduser()
        binary = binary if binary.is_absolute() else ROOT / binary
    else:
        found = shutil.which(executable, path=env.get("PATH"))
        binary = Path(found).parent if found else next((p for p in (
            Path(f"/opt/homebrew/opt/postgresql@{major}/bin"),
            Path(f"/usr/local/opt/postgresql@{major}/bin"),
        ) if (p / executable).is_file()), Path("/not-configured"))
    ctl = binary / executable
    ready = binary / ("pg_isready.exe" if os.name == "nt" else "pg_isready")
    if not ctl.is_file() or not ready.is_file():
        raise RuntimeError("Install the matching PostgreSQL tools or set OSII_DEV_POSTGRES_BIN to their bin directory")
    if dry_run:
        print(f"PostgreSQL: reuse or start {data} on {host}:{port} with {ctl}")
        return
    version = subprocess.run([str(ctl), "--version"], capture_output=True, text=True, check=True, timeout=5)
    installed_major = re.search(r"PostgreSQL\)\s+(\d+)", version.stdout)
    if not installed_major or installed_major.group(1) != major:
        raise RuntimeError(f"The configured PostgreSQL tools must match cluster version {major}")
    status = subprocess.run([str(ctl), "-D", str(data), "status"], capture_output=True, timeout=5)
    if status.returncode == 3:
        log = data.parent / "postgres.log"
        options = ["-p", str(port), "-h", "::1" if host == "::1" else "127.0.0.1"]
        if os.name != "nt":
            socket_dir = data.parent / "pg-socket"
            socket_dir.mkdir(mode=0o700, exist_ok=True)
            options += ["-k", str(socket_dir)]
        quoted = subprocess.list2cmdline(options) if os.name == "nt" else shlex.join(options)
        print(f"Starting PostgreSQL on {host}:{port}; log: {log}", flush=True)
        result = subprocess.run([str(ctl), "-D", str(data), "-l", str(log), "-w", "-t", "30", "-o", quoted, "start"],
            capture_output=True, timeout=40, start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        if result.returncode:
            raise RuntimeError(f"PostgreSQL did not start. Inspect {log}; no application services were started.")
    elif status.returncode != 0:
        raise RuntimeError(f"Could not check PostgreSQL cluster status at {data}")
    # Do not silently reuse a different server listening on DATABASE_URL's port.
    actual_port = int((data / "postmaster.pid").read_text().splitlines()[3])
    if actual_port != port:
        raise RuntimeError(f"The local PostgreSQL cluster is running on port {actual_port}, but DATABASE_URL uses {port}")
    probe = subprocess.run([str(ready), "-q", "-h", host, "-p", str(port), "-t", "3"], capture_output=True, timeout=5)
    if probe.returncode:
        raise RuntimeError(f"PostgreSQL is not accepting connections on {host}:{port}")
    print(f"PostgreSQL ready on {host}:{port} (left running when OSII stops)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-setup", action="store_true")
    args = parser.parse_args()
    env = {**load_dotenv(ROOT / ".env"), **os.environ}
    env["UV_PROJECT_ENVIRONMENT"] = str(ROOT / ".venv")
    env.setdefault("OSII_API_PORT", "8512")
    env.setdefault("OSII_DASHBOARD_PORT", "5174")
    env.setdefault("OSII_EXTRACTOR_URL", "http://127.0.0.1:8192")
    env.setdefault("OSII_PROCESSOR_GATEWAY_URL", f"http://127.0.0.1:{env['OSII_API_PORT']}/api/processor-model/v1")
    env.setdefault("OSII_SOURCE_DIR", str(ROOT / "osii-data/source"))
    for key in ("OSII_SOURCE_DIR", "OSII_MODEL_API_KEY_FILE", "OPENAI_API_KEY_FILE",
                "OSII_CHAT_API_KEY_FILE", "OSII_EMBEDDING_API_KEY_FILE", "OSII_RERANK_API_KEY_FILE"):
        if env.get(key):
            path = Path(env[key]).expanduser()
            env[key] = str(path if path.is_absolute() else ROOT / path)
    if not env.get("DATABASE_URL"):
        print("Set DATABASE_URL in .env. Run the explicit migration and administrator bootstrap first.", file=sys.stderr)
        return 1
    uv = shutil.which("uv")
    npm = shutil.which("npm")
    if not uv or (not args.core_only and not npm):
        print("Install uv and Node.js 22.18+ before make dev.", file=sys.stderr)
        return 1
    python = [str(ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))]
    services = [
        ("API", python + ["-m", "uvicorn", "osii.main:app", "--host", "127.0.0.1", "--port", env["OSII_API_PORT"]], ROOT / "osii-core"),
        ("Worker", python + ["-m", "osii.server.worker"], ROOT),
    ]
    if not args.core_only:
        services += [
            ("Extractor", python + ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8192"], ROOT / "osii-core/services/local-extractor"),
            ("Dashboard", [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", env["OSII_DASHBOARD_PORT"]], ROOT / "osii-dashboard/dashboard"),
        ]
    try:
        modules = [] if args.core_only else processor_modules(env)
    except ModuleManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for processor in modules:
        if processor.id in {name.lower() for name, _, _ in services}:
            print(f"{processor.manifest}: processor service ID conflicts with a server service", file=sys.stderr)
            return 1
        services.append((processor.id, module_command(processor, uv, env), processor.directory))
    urls = [value for value in env.get("OSII_PROCESSORS", "").split(",") if value]
    urls.extend(f"http://127.0.0.1:{processor.resolved_port(env)}" for processor in modules)
    env["OSII_PROCESSORS"] = ",".join(dict.fromkeys(urls))
    if args.dry_run:
        try:
            ensure_postgres(env, dry_run=True)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        for name, command, _ in services:
            print(name + ": " + shlex.join(command))
        return 0
    if not args.skip_setup:
        subprocess.run([uv, "sync", "--frozen", "--python", "3.12", "--package", "osii", "--extra", "server", "--extra", "rag-haystack"], cwd=ROOT, env=env, check=True)
        if not args.core_only and not (ROOT / "osii-dashboard/dashboard/node_modules").is_dir():
            subprocess.run([npm, "ci"], cwd=ROOT / "osii-dashboard/dashboard", env=env, check=True)
    processes = []
    if not args.skip_setup:
        prepared = set()
        for processor in modules:
            if processor.directory in prepared:
                continue
            subprocess.run([uv, "sync", "--python", "3.12", "--project", ".",
                *[arg for extra in processor.extras for arg in ("--extra", extra)]],
                cwd=processor.directory, env=service_environment(processor.id, env, modules), check=True)
            prepared.add(processor.directory)
    try:
        ensure_postgres(env)
        for name, command, cwd in services:
            if name == "Dashboard":
                for _ in range(80):
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:" + env["OSII_API_PORT"] + "/ready", timeout=1):
                            break
                    except OSError:
                        if any(p.poll() is not None for p in processes):
                            raise RuntimeError("A service failed; check database migration and configuration above")
                        time.sleep(.25)
                else:
                    raise RuntimeError("API readiness timed out")
            print("Starting " + name, flush=True)
            processes.append(subprocess.Popen(command, cwd=cwd, env=service_environment(name, env, modules),
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
        print("OSII-server dashboard: http://localhost:" + env["OSII_DASHBOARD_PORT"], flush=True)
        print("Ctrl+C stops application services; PostgreSQL stays running.", flush=True)
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("A service stopped unexpectedly")
            time.sleep(.5)
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
