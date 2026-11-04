"""Local startup must never initialize or manage an unintended database."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


spec = importlib.util.spec_from_file_location("server_dev_stack", Path(__file__).parents[2] / "scripts/dev_stack.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.fixture
def local(tmp_path):
    data = tmp_path / "postgres"
    data.mkdir()
    (data / "PG_VERSION").write_text("18\n")
    binary = tmp_path / "bin"
    binary.mkdir()
    for name in ("pg_ctl", "pg_isready"):
        (binary / (name + (".exe" if launcher.os.name == "nt" else ""))).touch()
    return {"OSII_DEV_POSTGRES_DIR": str(data), "OSII_DEV_POSTGRES_BIN": str(binary),
            "DATABASE_URL": "postgresql+psycopg://user:password-must-stay-private@127.0.0.1:55432/osii"}


def forbid_processes(monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("Must not manage PostgreSQL here"))


def test_external_database_is_not_managed(monkeypatch):
    forbid_processes(monkeypatch)
    launcher.ensure_postgres({"DATABASE_URL": "postgresql://user@external.test/database"})


def test_local_mode_refuses_remote_url_before_start(local, monkeypatch):
    forbid_processes(monkeypatch)
    local["DATABASE_URL"] = "postgresql://user:password-must-stay-private@external.test/database"
    with pytest.raises(RuntimeError, match="loopback") as error:
        launcher.ensure_postgres(local)
    assert "password-must-stay-private" not in str(error.value)


def test_missing_cluster_is_never_initialized(local, monkeypatch):
    forbid_processes(monkeypatch)
    path = Path(local["OSII_DEV_POSTGRES_DIR"]) / "missing"
    local["OSII_DEV_POSTGRES_DIR"] = str(path)
    with pytest.raises(RuntimeError, match="does not create databases"):
        launcher.ensure_postgres(local)
    assert not path.exists()


def test_dry_run_has_no_processes_or_secret_output(local, monkeypatch, capsys):
    forbid_processes(monkeypatch)
    launcher.ensure_postgres(local, dry_run=True)
    output = capsys.readouterr().out
    assert "55432" in output and "reuse or start" in output
    assert "password-must-stay-private" not in output
    assert not (Path(local["OSII_DEV_POSTGRES_DIR"]) / "postmaster.pid").exists()


def test_mismatched_major_version_cannot_start_cluster(local, monkeypatch):
    def run(args, **kwargs):
        assert args[-1] == "--version", "Must reject before starting the database"
        return subprocess.CompletedProcess(args, 0, stdout="pg_ctl (PostgreSQL) 17.6\n")
    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="version 18"):
        launcher.ensure_postgres(local)


def test_running_cluster_cannot_redirect_to_another_port(local, monkeypatch):
    data = Path(local["OSII_DEV_POSTGRES_DIR"])
    (data / "postmaster.pid").write_text("123\n/data\n0\n55433\n")
    def run(args, **kwargs):
        assert args[-1] in {"--version", "status"}, "Must not start or probe another database"
        return subprocess.CompletedProcess(args, 0, stdout="pg_ctl (PostgreSQL) 18.6 (Homebrew)\n")
    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="55433.*55432"):
        launcher.ensure_postgres(local)


def test_database_failure_prevents_application_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password-must-stay-private@localhost/osii")
    monkeypatch.setattr(sys, "argv", ["dev_stack.py", "--core-only", "--skip-setup"])
    monkeypatch.setattr(launcher.shutil, "which", lambda *a, **k: "/fake/uv")
    def fail(*a, **k):
        raise RuntimeError("Database unavailable")
    monkeypatch.setattr(launcher, "ensure_postgres", fail)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("Application must not start"))
    assert launcher.main() == 1
    assert "password-must-stay-private" not in capsys.readouterr().err
