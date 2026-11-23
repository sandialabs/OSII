"""Explicit local library selection. Never imports a checkout's environment."""
from __future__ import annotations

import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import tomllib
import uuid

from osii.library_lock import LibraryLock


def require_local(path: Path) -> None:
    if os.name == "nt":
        import ctypes
        get_type = ctypes.windll.kernel32.GetDriveTypeW
        get_type.argtypes = [ctypes.c_wchar_p]
        if get_type(path.anchor) == 4:
            raise ValueError("Library data and SQLite state must be on local disk. Documents may be on a shared drive.")
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("Library data must be on local disk; choose the share as the document folder instead.")


def validate_source(source: Path, library: Path) -> None:
    if not source.is_dir():
        raise ValueError("The document folder is unavailable. Connect the drive or choose another folder.")
    try:
        with os.scandir(source) as entries:
            next(entries, None)
    except OSError as exc:
        raise ValueError("The document folder cannot be read with your Windows account.") from exc
    if library.is_relative_to(source) or source.is_relative_to(library):
        raise ValueError("Choose separate folders for original documents and OSII library data.")


def check_library(root: Path, *, existing: bool) -> None:
    require_local(root)
    if existing:
        if not root.is_dir():
            raise ValueError("The selected library folder does not exist.")
        if not any((root / name).exists() for name in ("root.toml", "objects", "folders", "state/jobs.sqlite3", "state/inventory.sqlite3")):
            raise ValueError("Choose an existing OSII .osii library folder, not its document folder.")
        manifest = root / "root.toml"
        if manifest.is_file():
            try:
                value = tomllib.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ValueError("The library's root.toml cannot be read. Restore or repair it before opening.") from exc
            if value.get("schema_version", 1) != 1:
                raise ValueError("This library uses an unsupported sidecar format. No migration was performed.")
        inventory = root / "state" / "inventory.sqlite3"
        if inventory.exists():
            from osii.volume.store import SCHEMA_VERSION
            try:
                with closing(sqlite3.connect(inventory.as_uri() + "?mode=ro", uri=True)) as connection:
                    version = connection.execute("PRAGMA user_version").fetchone()[0]
                    if version != SCHEMA_VERSION:
                        raise ValueError("This inventory needs an explicit migration with a backup in OSII-local. Its evidence has not been changed.")
            except sqlite3.DatabaseError as exc:
                raise ValueError("The inventory database cannot be opened. Restore or repair it; OSII will not replace it.") from exc
        jobs = root / "state" / "jobs.sqlite3"
        if jobs.exists():
            try:
                with closing(sqlite3.connect(jobs.as_uri() + "?mode=ro", uri=True)) as connection:
                    required = {"id", "run_id", "payload_json", "status", "worker_id", "heartbeat_at"}
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(queue_jobs)")}
                    if not required.issubset(columns) or connection.execute("PRAGMA user_version").fetchone()[0] != 0:
                        raise ValueError("This job database uses an unsupported schema. Open it with its matching OSII-local version first.")
            except sqlite3.DatabaseError as exc:
                raise ValueError("The job database cannot be opened. No library data was replaced.") from exc
    elif root.exists() and any(root.iterdir()):
        raise ValueError("A new library must use an empty folder.")
    root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(dir=root):
            pass
    except OSError as exc:
        raise ValueError("The library folder is not writable. Choose a local folder owned by your account.") from exc


class Profiles:
    def __init__(self, data_directory: Path):
        self.directory = data_directory.resolve()
        require_local(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, identifier: str) -> Path:
        try:
            if str(uuid.UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid library profile") from exc
        return self.directory / "profiles" / identifier / "profile.json"

    def list(self) -> list[dict]:
        profiles = []
        for path in sorted((self.directory / "profiles").glob("*/profile.json")):
            try:
                profiles.append(self.get(path.parent.name))
            except (OSError, ValueError):
                continue
        return profiles

    def get(self, identifier: str) -> dict:
        profile = json.loads(self.path(identifier).read_text(encoding="utf-8"))
        if profile.get("version") != 1 or profile.get("id") != identifier:
            raise ValueError("Unsupported library profile version")
        return profile

    def create(self, *, source: str, name: str, library: str = "", config: str = "", existing: bool = False) -> dict:
        if not name.strip() or len(name) > 120:
            raise ValueError("Enter a library name of 1–120 characters.")
        identifier = str(uuid.uuid4())
        folder = self.path(identifier).parent
        if existing and not library.strip():
            raise ValueError("Choose the existing .osii library folder.")
        root = Path(library).expanduser().resolve() if existing else self.directory / "libraries" / identifier / ".osii"
        source_path = Path(source).expanduser().resolve()
        if not source.strip():
            raise ValueError("Choose the document folder.")
        validate_source(source_path, root)
        for profile in self.list():
            if Path(profile["library"]).resolve() == root:
                raise ValueError("This library already has a profile. Open it from the library list.")
        # Check ownership before inspecting databases. The lock is transient;
        # opening the profile acquires ownership again until all helpers stop.
        if existing and not root.is_dir():
            raise ValueError("The selected library folder does not exist.")
        if not existing:
            check_library(root, existing=False)
        require_local(root)
        with LibraryLock(root):
            if existing:
                check_library(root, existing=True)
        config_path = Path(config).expanduser().resolve() if config.strip() else folder / "config"
        require_local(config_path)
        if config_path.is_relative_to(source_path):
            raise ValueError("Configuration must be outside the document folder.")
        if config.strip() and not config_path.is_dir():
            raise ValueError("The selected existing configuration folder does not exist.")
        config_path.mkdir(parents=True, exist_ok=True)
        # An empty profile starts with no model connection; nothing is probed,
        # downloaded or silently copied from the previous checkout.
        models = config_path / "models.toml"
        if not models.exists() and not (config_path / "models.yml").exists():
            models.write_text("version = 1\n\n[models]\n\n[defaults]\n", encoding="utf-8")
        profile = {"version": 1, "id": identifier, "name": name.strip(), "source": str(source_path),
                   "library": str(root), "config": str(config_path)}
        if not existing:
            from osii.domain.storage.store import ensure_osii_store_layout
            ensure_osii_store_layout(root)
        folder.mkdir(parents=True, exist_ok=True)
        from osii.domain.storage.atomic import atomic_write_text
        atomic_write_text(self.path(identifier), json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
        return profile
