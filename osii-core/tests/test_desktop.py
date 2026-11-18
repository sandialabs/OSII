"""Delivery boundaries: explicit profiles, local data, private HTTP and reserved ports."""
import json
import os
from pathlib import Path
import socket
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from osii.desktop.http import attach_dashboard
from osii.desktop.profiles import Profiles, check_library
from osii.desktop.supervisor import Supervisor, listener
from osii.library_lock import LibraryLock


def test_new_profile_has_no_ambient_models_or_source_writes(tmp_path, monkeypatch):
    source = tmp_path / "Documents — evidence"
    source.mkdir()
    (source / "notes.txt").write_text("untouched")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-imported")
    profiles = Profiles(tmp_path / "application")
    profile = profiles.create(source=str(source), name="My library")
    assert list(source.iterdir()) == [source / "notes.txt"]
    assert Path(profile["library"]).is_relative_to(tmp_path / "application")
    assert Path(profile["config"]).joinpath("models.toml").read_text().endswith("[defaults]\n")
    assert not Path(profile["config"]).joinpath("secrets.env").exists()
    assert profiles.get(profile["id"]) == profile
    check_library(Path(profile["library"]), existing=True)


def test_open_library_preserves_existing_identity_and_blocks_another_owner(tmp_path):
    source, root = tmp_path / "documents", tmp_path / ".osii"
    source.mkdir()
    root.mkdir()
    original = '[root]\nroot_id="identity-kept"\n'
    (root / "root.toml").write_text(original)
    profiles = Profiles(tmp_path / "application")
    with LibraryLock(root):
        with pytest.raises(RuntimeError, match="already open"):
            profiles.create(source=str(source), name="Existing", library=str(root), existing=True)
    profile = profiles.create(source=str(source), name="Existing", library=str(root), existing=True)
    assert profile["library"] == str(root)
    assert (root / "root.toml").read_text() == original
    with pytest.raises(ValueError, match="already has a profile"):
        profiles.create(source=str(source), name="Duplicate", library=str(root), existing=True)


def test_invalid_inventory_is_never_replaced_or_migrated(tmp_path):
    root = tmp_path / ".osii"
    (root / "state").mkdir(parents=True)
    inventory = root / "state" / "inventory.sqlite3"
    with sqlite3.connect(inventory) as connection:
        connection.execute("PRAGMA user_version=1")
        connection.execute("CREATE TABLE evidence(text)")
        connection.execute("INSERT INTO evidence VALUES ('keep me')")
    before = inventory.read_bytes()
    with pytest.raises(ValueError, match="explicit migration"):
        check_library(root, existing=True)
    assert inventory.read_bytes() == before


def test_missing_and_unknown_libraries_do_not_get_silently_created(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        check_library(missing, existing=True)
    assert not missing.exists()
    missing.mkdir()
    with pytest.raises(ValueError, match="existing OSII"):
        check_library(missing, existing=True)


def test_profile_identifiers_cannot_escape_application_data(tmp_path):
    profiles = Profiles(tmp_path)
    for value in ("../elsewhere", "", "/tmp/elsewhere", "not-an-id"):
        with pytest.raises(ValueError):
            profiles.get(value)


def test_desktop_serves_spa_assets_but_never_masks_api_or_path_errors(tmp_path):
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "index.html").write_text("<html>compiled dashboard</html>")
    (dashboard / "app.js").write_text("// bundled asset")
    app = FastAPI()
    @app.get("/api/evidence")
    def evidence():
        return {"kept": True}
    attach_dashboard(app, dashboard, "private-token", port=19876)
    client = TestClient(app, base_url="http://127.0.0.1:19876")
    headers = {"Authorization": "Bearer private-token"}
    assert client.get("/", headers=headers).status_code == 200
    assert "compiled dashboard" in client.get("/research", headers=headers).text
    assert client.get("/api/evidence", headers=headers).json() == {"kept": True}
    assert client.get("/app.js", headers=headers).status_code == 200
    assert client.get("/api/missing", headers=headers).status_code == 404
    assert client.get("/assets/missing.js", headers=headers).status_code == 404
    assert client.get("/%2e%2e/outside.txt", headers=headers).status_code == 404
    assert "object-src 'none'" in client.get("/", headers=headers).headers["content-security-policy"]


def test_private_http_rejects_missing_tokens_foreign_origins_and_rebinding(tmp_path):
    (tmp_path / "index.html").write_text("desktop")
    app = FastAPI()
    attach_dashboard(app, tmp_path, "secret", port=19876)
    client = TestClient(app, base_url="http://127.0.0.1:19876")
    assert client.get("/").status_code == 403
    assert client.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get("/", headers={"Authorization": "Bearer secret", "Origin": "https://hostile.example"}).status_code == 403
    assert client.get("/", headers={"Authorization": "Bearer secret", "Host": "hostile.example"}).status_code == 403


def test_reserved_socket_cannot_be_taken_by_another_listener():
    first = listener()
    try:
        second = socket.socket()
        try:
            with pytest.raises(OSError):
                second.bind(first.getsockname())
        finally:
            second.close()
    finally:
        first.close()


@pytest.mark.skipif(os.name == "nt", reason="A Windows Job Object deliberately owns its calling process; tested in frozen subprocesses")
def test_supervisor_ignores_ambient_deployment_flags_and_exports_only_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://private")
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-export")
    monkeypatch.setenv("OSII_PROCESSORS", "http://unrelated.example")
    source = tmp_path / "source"
    source.mkdir()
    supervisor = Supervisor(tmp_path / "application")
    try:
        profile = supervisor.profiles.create(source=str(source), name="Test")
        ports = {name: 12345 + i for i, name in enumerate(["extractor", "ocr", "synthesizer", "embedder", "enricher", "model-bridge"])}
        env = supervisor.environment_for(profile, ports)
        assert env["OSII_STORAGE_BACKEND"] == "sidecar"
        assert env["OSII_NATIVE_EXTRACTOR_URL"] == "http://127.0.0.1:12345"
        assert "DATABASE_URL" not in env and "OPENAI_API_KEY" not in env
        assert "unrelated.example" not in env["OSII_PROCESSORS"]
        supervisor.record("extractor", "ready")
        supervisor.handler.flush()
        rows = [json.loads(line) for line in (tmp_path / "application/logs/lifecycle.jsonl").read_text().splitlines()]
        assert set(rows[0]) == {"time", "service", "event"}
    finally:
        supervisor.close()
