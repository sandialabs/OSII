from __future__ import annotations

import base64
from contextlib import closing
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import tomllib
from typing import Any


SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def catalog_path(osii_root: Path) -> Path:
    state = osii_root.resolve() / "state"
    state.mkdir(parents=True, exist_ok=True)
    return state / "catalog.sqlite3"


def _connect_path(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def connect_catalog(osii_root: Path) -> sqlite3.Connection:
    return _connect_path(catalog_path(osii_root))


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            file_id TEXT PRIMARY KEY,
            source_relpath TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            mime TEXT,
            suffix TEXT,
            size_bytes INTEGER,
            mtime_utc TEXT,
            sha256 TEXT,
            status TEXT NOT NULL,
            extractor_name TEXT,
            extractor_version TEXT,
            updated_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(source_relpath COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status, source_relpath COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_documents_suffix ON documents(suffix, source_relpath COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS extraction_variants (
            file_id TEXT NOT NULL,
            variant_id TEXT NOT NULL,
            extractor_name TEXT,
            extractor_version TEXT,
            status TEXT,
            created_utc TEXT,
            text_sha256 TEXT,
            text_chars INTEGER NOT NULL DEFAULT 0,
            manifest_records INTEGER NOT NULL DEFAULT 0,
            is_primary INTEGER NOT NULL DEFAULT 0,
            relpath TEXT NOT NULL,
            PRIMARY KEY (file_id, variant_id)
        );
        CREATE INDEX IF NOT EXISTS idx_extraction_variants_primary ON extraction_variants(file_id, is_primary);
        CREATE TABLE IF NOT EXISTS folders (
            folder_id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            parent_path TEXT,
            indexed_utc TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_folders_path ON folders(path COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            kind TEXT NOT NULL,
            color TEXT,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS collection_documents (
            collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            file_id TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            PRIMARY KEY (collection_id, file_id)
        );
        CREATE INDEX IF NOT EXISTS idx_collection_documents_file ON collection_documents(file_id);
        CREATE TABLE IF NOT EXISTS artifacts (
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            relpath TEXT NOT NULL,
            metadata_relpath TEXT,
            PRIMARY KEY (scope_type, scope_id, relpath)
        );
        CREATE TABLE IF NOT EXISTS semantic_indexes (
            index_id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            endpoint_type TEXT,
            model TEXT NOT NULL,
            model_digest TEXT,
            dimensions INTEGER,
            normalized INTEGER NOT NULL DEFAULT 0,
            semantic INTEGER NOT NULL DEFAULT 1,
            chunking_json TEXT,
            relpath TEXT NOT NULL,
            created_utc TEXT,
            compatible INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    now = utc_now()
    conn.execute(
        "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO catalog_meta(key, value) VALUES ('generated_utc', ?)",
        (now,),
    )


def _read_toml(path: Path) -> dict[str, Any] | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _normalize(path: Any) -> str:
    return str(path or "").replace("\\", "/").strip("/")


def _scan_documents(osii_root: Path, file_id: str | None = None) -> list[dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    folders = osii_root / "folders"
    if folders.exists():
        for manifest in folders.glob("folder-*.toml"):
            if manifest.name.endswith((".overview.toml", ".synth.toml")):
                continue
            data = _read_toml(manifest) or {}
            for item in data.get("docs", []):
                identifier = str(item.get("file_id") or "")
                relpath = _normalize(item.get("source_relpath"))
                if not identifier or not relpath or (file_id and identifier != file_id):
                    continue
                documents[identifier] = {
                    "file_id": identifier,
                    "source_relpath": relpath,
                    "filename": Path(relpath).name,
                    "mime": None,
                    "suffix": Path(relpath).suffix.lower(),
                    "size_bytes": None,
                    "mtime_utc": None,
                    "sha256": None,
                    "status": "done",
                    "extractor_name": None,
                    "extractor_version": None,
                    "updated_utc": utc_now(),
                }
    objects = osii_root / "objects"
    if objects.exists():
        candidates = [objects / file_id] if file_id else sorted(objects.iterdir())
        for object_dir in candidates:
            if not object_dir.is_dir():
                continue
            meta = _read_toml(object_dir / "meta.toml")
            provenance = _read_toml(object_dir / "provenance.toml")
            if not meta:
                continue
            status = str((provenance or {}).get("provenance", {}).get("status", "done" if object_dir.name in documents else "unknown"))
            if status not in {"done", "partial"}:
                continue
            file_data = meta.get("file", {})
            relpath = _normalize(file_data.get("source_relpath"))
            if not relpath:
                continue
            extractor = (provenance or {}).get("extractor", {})
            documents[object_dir.name] = {
                "file_id": object_dir.name,
                "source_relpath": relpath,
                "filename": str(file_data.get("filename") or Path(relpath).name),
                "mime": file_data.get("mime"),
                "suffix": Path(relpath).suffix.lower(),
                "size_bytes": file_data.get("size_bytes"),
                "mtime_utc": file_data.get("mtime_utc"),
                "sha256": meta.get("hash", {}).get("sha256"),
                "status": status,
                "extractor_name": extractor.get("name"),
                "extractor_version": extractor.get("version"),
                "updated_utc": (provenance or {}).get("provenance", {}).get("generated_utc") or utc_now(),
            }
    return list(documents.values())


def upsert_document(osii_root: Path, file_id: str) -> bool:
    """Reconcile one committed object without delaying the rest of Intake."""
    ensure_catalog(osii_root)
    documents = _scan_documents(osii_root.resolve(), file_id)
    if not documents:
        return False
    document = documents[0]
    with closing(connect_catalog(osii_root)) as conn:
        conn.execute(
            """INSERT INTO documents VALUES (:file_id, :source_relpath, :filename, :mime, :suffix,
            :size_bytes, :mtime_utc, :sha256, :status, :extractor_name, :extractor_version, :updated_utc)
            ON CONFLICT(file_id) DO UPDATE SET
              source_relpath=excluded.source_relpath, filename=excluded.filename, mime=excluded.mime,
              suffix=excluded.suffix, size_bytes=excluded.size_bytes, mtime_utc=excluded.mtime_utc,
              sha256=excluded.sha256, status=excluded.status, extractor_name=excluded.extractor_name,
              extractor_version=excluded.extractor_version, updated_utc=excluded.updated_utc""",
            document,
        )
        conn.commit()
    return True


def _scan_folders(osii_root: Path) -> list[dict[str, Any]]:
    folders: list[dict[str, Any]] = []
    directory = osii_root / "folders"
    if not directory.exists():
        return folders
    for path in sorted(directory.glob("folder-*.toml")):
        if path.name.endswith((".overview.toml", ".synth.toml")):
            continue
        data = _read_toml(path)
        node = (data or {}).get("node", {})
        folder_id = node.get("folder_id")
        relpath = _normalize(node.get("path_hint"))
        if not folder_id:
            continue
        folders.append(
            {
                "folder_id": str(folder_id),
                "path": relpath,
                "parent_path": str(Path(relpath).parent).replace("\\", "/") if relpath else None,
                "indexed_utc": node.get("indexed_utc") or "",
            }
        )
    return folders


def _scan_collections(osii_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    collections: list[dict[str, Any]] = []
    members: list[dict[str, str]] = []
    directory = osii_root / "collections"
    if not directory.exists():
        return collections, members
    for collection_dir in sorted(directory.iterdir()):
        if not collection_dir.is_dir():
            continue
        data = _read_toml(collection_dir / "collection.toml")
        if not data:
            continue
        record = data.get("collection", data)
        collection_id = str(record.get("id") or collection_dir.name)
        collections.append(
            {
                "id": collection_id,
                "name": str(record.get("name") or collection_id),
                "description": record.get("description"),
                "kind": str(record.get("kind") or "manual"),
                "color": record.get("color"),
                "created_utc": str(record.get("created_utc") or utc_now()),
                "updated_utc": str(record.get("updated_utc") or utc_now()),
            }
        )
        membership = collection_dir / "members.jsonl"
        if membership.exists():
            for line in membership.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("file_id"):
                    members.append(
                        {
                            "collection_id": collection_id,
                            "file_id": str(item["file_id"]),
                            "created_utc": str(item.get("created_utc") or utc_now()),
                        }
                    )
    return collections, members


def _scan_artifacts(osii_root: Path) -> list[tuple[str, str, str, str, str | None]]:
    records: dict[tuple[str, str, str], tuple[str, str, str, str, str | None]] = {}

    def add_tree(scope_type: str, scope_id: str, directory: Path, kind: str) -> None:
        if not directory.is_dir():
            return
        for path in directory.rglob("*"):
            if not path.is_file() or path.name.endswith((".meta.toml", ".toml")):
                continue
            metadata_candidates = [path.with_name(path.name + ".meta.toml"), path.with_suffix(".toml")]
            metadata = next((candidate for candidate in metadata_candidates if candidate.exists()), None)
            relpath = path.relative_to(osii_root).as_posix()
            records[(scope_type, scope_id, relpath)] = (scope_type, scope_id, kind, relpath, metadata.relative_to(osii_root).as_posix() if metadata else None)

    objects = osii_root / "objects"
    if objects.exists():
        for scope in objects.iterdir():
            if not scope.is_dir():
                continue
            add_tree("object", scope.name, scope / "artifacts", "extraction")
            add_tree("object", scope.name, scope / "syntheses", "synthesis")
            add_tree("object", scope.name, scope / "enrichments", "enrichment")
            if (scope / "synth.txt").is_file():
                path = scope / "synth.txt"
                records[("object", scope.name, path.relative_to(osii_root).as_posix())] = ("object", scope.name, "synthesis", path.relative_to(osii_root).as_posix(), (scope / "synth.toml").relative_to(osii_root).as_posix() if (scope / "synth.toml").exists() else None)
    folders = osii_root / "folders"
    if folders.exists():
        for directory in folders.glob("folder-*.syntheses"):
            add_tree("folder", directory.name.removeprefix("folder-").removesuffix(".syntheses"), directory, "synthesis")
        for directory in folders.glob("folder-*.enrichments"):
            add_tree("folder", directory.name.removeprefix("folder-").removesuffix(".enrichments"), directory, "enrichment")
    collections = osii_root / "collections"
    if collections.exists():
        for scope in collections.iterdir():
            if scope.is_dir():
                add_tree("collection", scope.name, scope / "syntheses", "synthesis")
                add_tree("collection", scope.name, scope / "enrichments", "enrichment")
    add_tree("root", "root", osii_root / "syntheses", "synthesis")
    add_tree("root", "root", osii_root / "enrichments", "enrichment")
    return list(records.values())


def _scan_extraction_variants(osii_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    objects = osii_root / "objects"
    if not objects.is_dir():
        return records
    for obj in objects.iterdir():
        index_path = obj / "extractions" / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        primary_id = index.get("primary_id")
        for variant in index.get("variants") or []:
            variant_id = str(variant.get("id") or "")
            if not variant_id:
                continue
            extractor = variant.get("extractor") or {}
            records.append({
                "file_id": obj.name,
                "variant_id": variant_id,
                "extractor_name": extractor.get("name"),
                "extractor_version": extractor.get("version"),
                "status": variant.get("status"),
                "created_utc": variant.get("created_utc"),
                "text_sha256": variant.get("text_sha256"),
                "text_chars": int(variant.get("text_chars") or 0),
                "manifest_records": int(variant.get("manifest_records") or 0),
                "is_primary": variant_id == primary_id,
                "relpath": f"objects/{obj.name}/extractions/{variant_id}",
            })
    return records


def _scan_indexes(osii_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in (osii_root / "embeddings").rglob("segments.meta.toml") if (osii_root / "embeddings").exists() else []:
        data = _read_toml(path) or {}
        meta = data.get("embeddings", data.get("index", {}))
        provider = str(meta.get("provider_id") or meta.get("provider") or meta.get("embedder") or "unknown")
        model = str(meta.get("model") or "unknown")
        index_id = base64.urlsafe_b64encode(f"{provider}\0{model}\0{path}".encode()).decode().rstrip("=")
        records.append({
            "index_id": index_id,
            "provider_id": provider,
            "endpoint_type": meta.get("endpoint_type"),
            "model": model,
            "model_digest": meta.get("model_digest"),
            "dimensions": meta.get("dimensions") or meta.get("dimension"),
            "normalized": bool(meta.get("normalized", False)),
            "semantic": bool(meta.get("semantic", provider != "local.hashing")),
            "chunking_json": json.dumps(data.get("chunking", {}), sort_keys=True),
            "relpath": path.parent.relative_to(osii_root).as_posix(),
            "created_utc": meta.get("created_utc") or meta.get("generated_utc"),
            "compatible": bool(meta.get("compatible", True)),
        })
    return records


def _populate(conn: sqlite3.Connection, osii_root: Path) -> None:
    for document in _scan_documents(osii_root):
        conn.execute(
            """INSERT INTO documents VALUES (:file_id, :source_relpath, :filename, :mime, :suffix,
            :size_bytes, :mtime_utc, :sha256, :status, :extractor_name, :extractor_version, :updated_utc)""",
            document,
        )
    for folder in _scan_folders(osii_root):
        conn.execute("INSERT INTO folders VALUES (:folder_id, :path, :parent_path, :indexed_utc)", folder)
    collections, members = _scan_collections(osii_root)
    for collection in collections:
        conn.execute("INSERT INTO collections VALUES (:id, :name, :description, :kind, :color, :created_utc, :updated_utc)", collection)
    for member in members:
        conn.execute("INSERT OR IGNORE INTO collection_documents VALUES (:collection_id, :file_id, :created_utc)", member)
    for artifact in _scan_artifacts(osii_root):
        conn.execute("INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)", artifact)
    for variant in _scan_extraction_variants(osii_root):
        conn.execute(
            """INSERT INTO extraction_variants VALUES (:file_id, :variant_id, :extractor_name,
            :extractor_version, :status, :created_utc, :text_sha256, :text_chars,
            :manifest_records, :is_primary, :relpath)""",
            variant,
        )
    for index in _scan_indexes(osii_root):
        conn.execute(
            """INSERT INTO semantic_indexes VALUES (:index_id, :provider_id, :endpoint_type, :model, :model_digest,
            :dimensions, :normalized, :semantic, :chunking_json, :relpath, :created_utc, :compatible)""",
            index,
        )


def rebuild_catalog(osii_root: Path) -> dict[str, Any]:
    osii_root = osii_root.resolve()
    target = catalog_path(osii_root)
    descriptor, temporary_name = tempfile.mkstemp(prefix="catalog-", suffix=".sqlite3", dir=target.parent)
    # mkstemp leaves its descriptor open. SQLite opens the path separately, so
    # retain only the path and release the original handle before Windows sees
    # the file as locked during cleanup.
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        # sqlite3.Connection's context manager commits or rolls back but does
        # not close the connection. Windows will not replace or remove an open
        # SQLite file, so closing() is required before the atomic swap below.
        with closing(_connect_path(temporary)) as conn:
            create_schema(conn)
            _populate(conn, osii_root)
            conn.commit()
            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("documents", "extraction_variants", "folders", "collections", "artifacts", "semantic_indexes")
            }
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        target.with_name(target.name + "-wal").unlink(missing_ok=True)
        target.with_name(target.name + "-shm").unlink(missing_ok=True)
        os.replace(temporary, target)
        return {"status": "ready", "path": str(target), "schema_version": SCHEMA_VERSION, "counts": counts}
    finally:
        temporary.unlink(missing_ok=True)
        temporary.with_name(temporary.name + "-wal").unlink(missing_ok=True)
        temporary.with_name(temporary.name + "-shm").unlink(missing_ok=True)


def verify_catalog(osii_root: Path) -> dict[str, Any]:
    path = catalog_path(osii_root)
    if not path.exists():
        return {"status": "missing", "path": str(path), "ok": False}
    try:
        with closing(connect_catalog(osii_root)) as conn:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            version = conn.execute("SELECT value FROM catalog_meta WHERE key='schema_version'").fetchone()
            generated = conn.execute("SELECT value FROM catalog_meta WHERE key='generated_utc'").fetchone()
            counts = {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("documents", "folders", "collections")}
        return {"status": "ready" if integrity == "ok" else "corrupt", "ok": integrity == "ok" and bool(version) and int(version[0]) == SCHEMA_VERSION, "integrity": integrity, "schema_version": int(version[0]) if version else None, "generation": generated[0] if generated else None, "rebuilding": False, "counts": counts, "path": str(path)}
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        return {"status": "corrupt", "ok": False, "detail": str(exc), "path": str(path)}


def ensure_catalog(osii_root: Path) -> dict[str, Any]:
    status = verify_catalog(osii_root)
    if status.get("ok"):
        return status
    path = catalog_path(osii_root)
    if path.exists():
        quarantine = path.with_name(f"catalog.corrupt-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sqlite3")
        shutil.move(path, quarantine)
    return rebuild_catalog(osii_root)


def _encode_cursor(source_relpath: str, file_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([source_relpath, file_id]).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    padding = "=" * (-len(cursor) % 4)
    values = json.loads(base64.urlsafe_b64decode(cursor + padding))
    return str(values[0]), str(values[1])


def list_documents(
    osii_root: Path,
    *,
    limit: int = 100,
    cursor: str | None = None,
    status: str | None = None,
    suffix: str | None = None,
    path: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    ensure_catalog(osii_root)
    where: list[str] = []
    values: list[Any] = []
    if status:
        where.append("status = ?")
        values.append(status)
    if suffix:
        where.append("suffix = ?")
        values.append(suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}")
    if path:
        where.append("source_relpath LIKE ? ESCAPE '\\'")
        values.append(path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if text:
        where.append("(source_relpath LIKE ? OR filename LIKE ?)")
        values.extend([f"%{text}%", f"%{text}%"])
    if cursor:
        cursor_path, cursor_id = _decode_cursor(cursor)
        where.append("(source_relpath COLLATE NOCASE > ? COLLATE NOCASE OR (source_relpath = ? AND file_id > ?))")
        values.extend([cursor_path, cursor_path, cursor_id])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = min(max(1, limit), 500)
    with closing(connect_catalog(osii_root)) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM documents {clause}", values).fetchone()[0])
        rows = conn.execute(f"SELECT * FROM documents {clause} ORDER BY source_relpath COLLATE NOCASE, file_id LIMIT ?", (*values, limit + 1)).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [dict(row) for row in rows]
    next_cursor = _encode_cursor(rows[-1]["source_relpath"], rows[-1]["file_id"]) if has_more and rows else None
    return {"items": items, "total": total, "limit": limit, "next_cursor": next_cursor}


def list_folders(osii_root: Path) -> list[dict[str, Any]]:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        return [dict(row) for row in conn.execute("SELECT folder_id, path, indexed_utc AS last_seen_utc FROM folders ORDER BY path COLLATE NOCASE")]


def page_folders(osii_root: Path, *, limit: int = 100, cursor: str | None = None, path: str | None = None, text: str | None = None) -> dict[str, Any]:
    ensure_catalog(osii_root)
    where: list[str] = []
    values: list[Any] = []
    if path:
        where.append("path LIKE ?")
        values.append(path.replace("\\", "/").strip("/") + "%")
    if text:
        where.append("path LIKE ?")
        values.append(f"%{text}%")
    if cursor:
        cursor_path, cursor_id = _decode_cursor(cursor)
        where.append("(path COLLATE NOCASE > ? COLLATE NOCASE OR (path = ? AND folder_id > ?))")
        values.extend([cursor_path, cursor_path, cursor_id])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit = min(max(1, limit), 500)
    with closing(connect_catalog(osii_root)) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM folders {clause}", values).fetchone()[0])
        rows = conn.execute(f"SELECT folder_id, path, indexed_utc AS last_seen_utc FROM folders {clause} ORDER BY path COLLATE NOCASE, folder_id LIMIT ?", (*values, limit + 1)).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "next_cursor": _encode_cursor(rows[-1]["path"], rows[-1]["folder_id"]) if has_more and rows else None}


def list_collection_records(osii_root: Path) -> list[dict[str, Any]]:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        rows = conn.execute("""SELECT c.*, COUNT(cd.file_id) AS document_count FROM collections c LEFT JOIN collection_documents cd ON cd.collection_id=c.id GROUP BY c.id ORDER BY lower(c.name)""").fetchall()
    return [dict(row) for row in rows]


def get_collection_record(osii_root: Path, collection_id: str) -> dict[str, Any] | None:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        row = conn.execute("""SELECT c.*, COUNT(cd.file_id) AS document_count FROM collections c LEFT JOIN collection_documents cd ON cd.collection_id=c.id WHERE c.id=? GROUP BY c.id""", (collection_id,)).fetchone()
    return dict(row) if row else None


def get_collection_member_ids(osii_root: Path, collection_id: str) -> list[str]:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        return [str(row[0]) for row in conn.execute("SELECT file_id FROM collection_documents WHERE collection_id=? ORDER BY created_utc, file_id", (collection_id,))]


def get_file_collection_records(osii_root: Path, file_id: str) -> list[dict[str, Any]]:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        rows = conn.execute("""SELECT c.id, c.name, c.kind FROM collections c JOIN collection_documents cd ON cd.collection_id=c.id WHERE cd.file_id=? ORDER BY lower(c.name)""", (file_id,)).fetchall()
    return [dict(row) for row in rows]


def list_artifact_records(osii_root: Path, *, scope_type: str | None = None, scope_id: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    ensure_catalog(osii_root)
    where: list[str] = []
    values: list[str] = []
    for column, value in (("scope_type", scope_type), ("scope_id", scope_id), ("kind", kind)):
        if value:
            where.append(f"{column} = ?")
            values.append(value)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with closing(connect_catalog(osii_root)) as conn:
        rows = conn.execute(f"SELECT * FROM artifacts {clause} ORDER BY scope_type, scope_id, kind, relpath", values).fetchall()
    return [dict(row) for row in rows]


def list_semantic_indexes(osii_root: Path) -> list[dict[str, Any]]:
    ensure_catalog(osii_root)
    with closing(connect_catalog(osii_root)) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM semantic_indexes ORDER BY created_utc DESC, provider_id, model")]
