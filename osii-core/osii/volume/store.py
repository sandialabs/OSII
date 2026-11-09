"""Canonical SQLite evidence and operational state, with explicit schema versions."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Iterator

from .models import Filters, ProcessRequest, SelectionRequest, ScanOptions

SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL UNIQUE,
 device TEXT NOT NULL, inode TEXT NOT NULL);
CREATE TABLE runs(
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, source_id INTEGER REFERENCES sources,
 selection_id INTEGER, payload TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'queued',
 owner TEXT, lease_until REAL, created REAL NOT NULL, updated REAL NOT NULL,
 completed INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
 bytes_read INTEGER NOT NULL DEFAULT 0, elapsed REAL NOT NULL DEFAULT 0, error TEXT);
CREATE INDEX runs_queue ON runs(status,id);
CREATE TABLE directories(
 run_id INTEGER NOT NULL REFERENCES runs, path TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', error TEXT, PRIMARY KEY(run_id,path));
CREATE INDEX directories_queue ON directories(run_id,status,path);
CREATE TABLE extractions(
 id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, processor_key TEXT NOT NULL,
 response TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL,
 UNIQUE(sha256,processor_key));
CREATE TABLE entries(
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources,
 path TEXT NOT NULL, parent TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
 suffix TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
 ctime_ns INTEGER NOT NULL, device TEXT, inode TEXT,
 revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'present',
 observed REAL NOT NULL, seen_token TEXT NOT NULL,
 extraction_id TEXT REFERENCES extractions, UNIQUE(source_id,path));
CREATE INDEX entries_parent ON entries(source_id,parent,status);
CREATE INDEX entries_suffix ON entries(suffix,status,id);
CREATE INDEX entries_size ON entries(size_bytes,status,id);
CREATE INDEX entries_extraction ON entries(extraction_id,status);
CREATE TABLE entry_extractions(
 entry_id INTEGER NOT NULL REFERENCES entries, revision INTEGER NOT NULL,
 extraction_id TEXT NOT NULL REFERENCES extractions,
 PRIMARY KEY(entry_id,revision,extraction_id));
CREATE TABLE selections(
 id INTEGER PRIMARY KEY, request TEXT NOT NULL, created REAL NOT NULL,
 count INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0);
CREATE TABLE selection_members(
 selection_id INTEGER NOT NULL REFERENCES selections, entry_id INTEGER NOT NULL REFERENCES entries,
 revision INTEGER NOT NULL, PRIMARY KEY(selection_id,entry_id));
CREATE TABLE work_items(
 run_id INTEGER NOT NULL REFERENCES runs, entry_id INTEGER NOT NULL REFERENCES entries,
 revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', error TEXT,
 seconds REAL NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0,
 text_chars INTEGER NOT NULL DEFAULT 0, extraction_id TEXT REFERENCES extractions,
 PRIMARY KEY(run_id,entry_id));
CREATE INDEX work_queue ON work_items(run_id,status,entry_id);
CREATE TABLE products(
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs,
 entry_id INTEGER NOT NULL REFERENCES entries, extraction_id TEXT NOT NULL REFERENCES extractions,
 kind TEXT NOT NULL, response TEXT NOT NULL, created REAL NOT NULL,
 UNIQUE(run_id,entry_id));
CREATE TABLE events(
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs,
 created REAL NOT NULL, path TEXT, message TEXT NOT NULL);
CREATE INDEX events_run ON events(run_id,id);
CREATE VIRTUAL TABLE text_search USING fts5(text, content='extractions', content_rowid='rowid');
CREATE TRIGGER extraction_insert AFTER INSERT ON extractions BEGIN
 INSERT INTO text_search(rowid,text) VALUES(new.rowid,new.text);
END;
"""

MIGRATION_2 = """
ALTER TABLE sources ADD COLUMN generation INTEGER NOT NULL DEFAULT 1;
ALTER TABLE entries ADD COLUMN metadata_state TEXT NOT NULL DEFAULT 'known';
ALTER TABLE entries ADD COLUMN metadata_error TEXT;
ALTER TABLE entries ADD COLUMN scan_run_id INTEGER;
ALTER TABLE directories ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE directories ADD COLUMN updated REAL;
ALTER TABLE runs ADD COLUMN observed_entries INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN known_bytes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN metadata_errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE selections ADD COLUMN coverage TEXT NOT NULL DEFAULT '{}';
ALTER TABLE selection_members ADD COLUMN source_id INTEGER;
ALTER TABLE selection_members ADD COLUMN path TEXT;
ALTER TABLE selection_members ADD COLUMN size_bytes INTEGER;
ALTER TABLE selection_members ADD COLUMN mtime_ns INTEGER;
ALTER TABLE selection_members ADD COLUMN ctime_ns INTEGER;
ALTER TABLE selection_members ADD COLUMN source_generation INTEGER;
ALTER TABLE selection_members ADD COLUMN file_device TEXT;
ALTER TABLE selection_members ADD COLUMN file_inode TEXT;
UPDATE selection_members SET
 source_id=(SELECT source_id FROM entries WHERE id=entry_id),
 path=(SELECT path FROM entries WHERE id=entry_id),
 size_bytes=(SELECT size_bytes FROM entries WHERE id=entry_id),
 mtime_ns=(SELECT mtime_ns FROM entries WHERE id=entry_id),
 ctime_ns=(SELECT ctime_ns FROM entries WHERE id=entry_id),
 source_generation=(SELECT s.generation FROM entries e JOIN sources s ON s.id=e.source_id WHERE e.id=entry_id),
 file_device=(SELECT device FROM entries WHERE id=entry_id),
 file_inode=(SELECT inode FROM entries WHERE id=entry_id);
CREATE TABLE sidecar_links(entry_id INTEGER NOT NULL, revision INTEGER NOT NULL,
 file_id TEXT NOT NULL, run_id TEXT NOT NULL, updated REAL NOT NULL,
 PRIMARY KEY(entry_id,revision));
CREATE TABLE intake_handoffs(selection_id INTEGER NOT NULL, request_key TEXT NOT NULL,
 run_id TEXT NOT NULL UNIQUE, created REAL NOT NULL, PRIMARY KEY(selection_id,request_key));
CREATE INDEX entries_source_observed ON entries(source_id,status,id);
CREATE INDEX runs_source_kind ON runs(source_id,kind,id);
"""


def _statements(conn: sqlite3.Connection, sql: str) -> None:
    statement = ""
    for line in sql.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""


def database_path(osii_root: Path | None = None) -> Path:
    root = osii_root or Path(os.getenv("OSII_ROOT", "./data_volume/.osii"))
    # Honor an explicitly configured pilot database without migrating it.
    configured = os.getenv("OSII_INVENTORY_DB", "") or os.getenv("OSII_VOLUME_DB", "")
    return (
        Path(configured or root / "state" / "inventory.sqlite3").expanduser().resolve()
    )


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def prefix_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def predicate(filters: Filters, alias: str = "e") -> tuple[str, list]:
    terms = [f"{alias}.kind IN ('file','unknown')", f"{alias}.status='present'"]
    values: list = []
    if filters.source_id is not None:
        terms.append(f"{alias}.source_id=?")
        values.append(filters.source_id)
    if filters.path:
        # Inventory paths use '/' separators. A backslash is a legal POSIX
        # filename character and must not be silently changed into a separator.
        path = filters.path.strip("/")
        terms.append(f"({alias}.path=? OR {alias}.path LIKE ? ESCAPE '\\')")
        values.extend([path, prefix_like(path) + "/%"])
    if filters.name:
        terms.append(f"{alias}.name LIKE ? ESCAPE '\\'")
        values.append("%" + prefix_like(filters.name) + "%")
    if filters.suffix:
        terms.append(f"{alias}.suffix=?")
        values.append("." + filters.suffix.lower().lstrip("."))
    if filters.text_state != "any":
        terms.append(
            f"{alias}.extraction_id IS {'NULL' if filters.text_state == 'metadata_only' else 'NOT NULL'}"
        )
    if filters.metadata_state != "any":
        terms.append(f"{alias}.metadata_state=?")
        values.append(filters.metadata_state)
    if filters.sidecar_state != "any":
        terms.append(
            f"{'NOT ' if filters.sidecar_state == 'missing' else ''}EXISTS (SELECT 1 FROM sidecar_links l WHERE l.entry_id={alias}.id AND l.revision={alias}.revision)"
        )
    if filters.min_bytes or filters.max_bytes is not None:
        terms.append(f"{alias}.metadata_state='known' AND {alias}.size_bytes>=?")
        values.append(filters.min_bytes)
    if filters.max_bytes is not None:
        terms.append(f"{alias}.size_bytes<=?")
        values.append(filters.max_bytes)
    for attribute, operator in (("modified_after", ">="), ("modified_before", "<")):
        value = getattr(filters, attribute)
        if value is not None:
            terms.append(f"{alias}.metadata_state='known'")
            terms.append(f"{alias}.mtime_ns{operator}?")
            values.append(
                (value + (1 if attribute == "modified_before" else 0)) * 1_000_000_000
            )
    return " AND ".join(terms), values


class VolumeStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("PRAGMA case_sensitive_like=ON")
        conn.create_function(
            "sample_key",
            2,
            lambda seed, key: hashlib.sha256(f"{seed}:{key}".encode()).hexdigest(),
            deterministic=True,
        )
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # API and worker can start simultaneously; schema inspection and
            # creation must share one lock, without executescript's implicit commit.
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                if (
                    version != 0
                    or conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
                    ).fetchone()
                ):
                    raise ValueError(
                        "Inventory schema requires an explicit migration. Stop OSII and run python -m osii.volume migrate --backup PATH; evidence has not been reset."
                    )
                _statements(conn, SCHEMA)
                _statements(conn, MIGRATION_2)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()
            conn.execute("PRAGMA journal_mode=WAL")

    def migrate(self, backup: Path) -> None:
        with self.connect() as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Migration requires an existing version 1 inventory")
            if conn.execute(
                "SELECT 1 FROM runs WHERE owner IS NOT NULL AND lease_until>?",
                (time.time(),),
            ).fetchone():
                raise ValueError(
                    "Stop the inventory worker and wait for its lease to end before migration"
                )
        self.backup(backup)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Inventory schema changed during migration")
            if conn.execute(
                "SELECT 1 FROM runs WHERE owner IS NOT NULL AND lease_until>?",
                (time.time(),),
            ).fetchone():
                raise ValueError(
                    "Inventory worker restarted during migration; stop it before retrying"
                )
            _statements(conn, MIGRATION_2)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def register_source(self, root: Path, name: str = "") -> dict:
        root = Path(root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Source must be an existing directory")
        if self.path.is_relative_to(root):
            raise ValueError("The canonical database must be outside every source root")
        with self.connect() as conn:
            # Overlapping sources make identity and coverage ambiguous.
            for row in conn.execute("SELECT root FROM sources"):
                other = Path(row["root"])
                if root != other and (
                    root.is_relative_to(other) or other.is_relative_to(root)
                ):
                    raise ValueError("Source roots must not overlap")
            info = root.stat()
            conn.execute(
                "INSERT INTO sources(name,root,device,inode) VALUES(?,?,?,?) ON CONFLICT(root) DO NOTHING",
                (name or root.name, str(root), str(info.st_dev), str(info.st_ino)),
            )
            previous = conn.execute(
                "SELECT device,inode FROM sources WHERE root=?", (str(root),)
            ).fetchone()
            if (previous["device"], previous["inode"]) != (
                str(info.st_dev),
                str(info.st_ino),
            ):
                raise ValueError(
                    "Source root identity changed; reconnect the original root before scanning"
                )
            return dict(
                conn.execute(
                    "SELECT * FROM sources WHERE root=?", (str(root),)
                ).fetchone()
            )

    def source(self, source_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE id=?", (source_id,)
            ).fetchone()
            if not row:
                raise KeyError("Source not found")
            return dict(row)

    def sources(self) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY id")
            ]

    def source_scans(self, source_id: int) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM runs WHERE source_id=? AND kind='scan' ORDER BY id DESC LIMIT 20",
                    (source_id,),
                )
            ]

    def rebind_source(self, source_id: int, confirmed_root: str) -> dict:
        source = self.source(source_id)
        if confirmed_root != source["root"]:
            raise ValueError(
                "Confirm the exact registered root after verifying the mounted dataset"
            )
        root = Path(confirmed_root)
        if root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError(
                "The registered directory must be mounted at its original path"
            )
        info = root.stat()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM runs WHERE source_id=? AND (status IN ('running','queued','paused') OR (owner IS NOT NULL AND lease_until>?))",
                (source_id, time.time()),
            ).fetchone():
                raise ValueError(
                    "Cancel active scans and wait for the worker to release them before rebinding"
                )
            conn.execute(
                "UPDATE sources SET device=?,inode=?,generation=generation+1 WHERE id=?",
                (str(info.st_dev), str(info.st_ino), source_id),
            )
            conn.execute(
                "UPDATE entries SET status='unverified',revision=revision+1,scan_run_id=NULL,extraction_id=NULL WHERE source_id=?",
                (source_id,),
            )
        return self.source(source_id)

    def new_scan(self, source_id: int, options: ScanOptions | None = None) -> int:
        source = self.source(source_id)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM runs WHERE kind='scan' AND source_id=? AND status IN ('queued','running','paused')",
                (source_id,),
            ).fetchone():
                raise ValueError(
                    "Resume or cancel the existing scan before starting another"
                )
            now = time.time()
            run_id = conn.execute(
                "INSERT INTO runs(kind,source_id,payload,created,updated) VALUES('scan',?,?,?,?)",
                (
                    source_id,
                    encode(
                        {
                            **(options or ScanOptions()).model_dump(),
                            "source_generation": source["generation"],
                        }
                    ),
                    now,
                    now,
                ),
            ).lastrowid
            conn.execute("INSERT INTO directories(run_id,path) VALUES(?,'')", (run_id,))
            return run_id

    def summary(self, filters: Filters) -> dict:
        where, values = predicate(filters)
        with self.connect() as conn:
            row = dict(
                conn.execute(
                    f"SELECT count(*) AS files,coalesce(sum(CASE WHEN metadata_state='known' THEN size_bytes ELSE 0 END),0) AS bytes, count(extraction_id) AS extracted,coalesce(sum(metadata_state!='known'),0) AS unknown_sizes FROM entries e WHERE {where}",
                    values,
                ).fetchone()
            )
            row["formats"] = [
                dict(r)
                for r in conn.execute(
                    f"SELECT suffix,count(*) AS files,sum(size_bytes) AS bytes FROM entries e WHERE {where} GROUP BY suffix ORDER BY files DESC LIMIT 100",
                    values,
                )
            ]
            row["scan_status"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT r.id,r.source_id,r.status,r.completed,r.failed,r.updated FROM runs r WHERE kind='scan' AND r.id=(SELECT max(id) FROM runs x WHERE x.kind='scan' AND x.source_id=r.source_id)"
                    + (" AND r.source_id=?" if filters.source_id is not None else ""),
                    [filters.source_id] if filters.source_id is not None else [],
                )
            ]
            return row

    def entries(self, filters: Filters, after: int = 0, limit: int = 100) -> dict:
        where, values = predicate(filters)
        with self.connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    f"SELECT e.* FROM entries e WHERE {where} AND e.id>? ORDER BY e.id LIMIT ?",
                    [*values, after, limit + 1],
                )
            ]
        for row in rows:
            if row["metadata_state"] != "known":
                row["size_bytes"] = row["mtime_ns"] = row["ctime_ns"] = None
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def folders(
        self, source_id: int, parent: str = "", after: int = 0, limit: int = 100
    ) -> dict:
        with self.connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id,path,status,observed FROM entries WHERE source_id=? AND parent=? AND kind='directory' AND id>? ORDER BY id LIMIT ?",
                    (source_id, parent, after, limit + 1),
                )
            ]
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def select(self, request: SelectionRequest) -> dict:
        where, values = predicate(request.filters)
        where += " AND e.metadata_state='known' AND e.kind='file' AND e.size_bytes<=?"
        where += " AND e.scan_run_id=(SELECT max(r.id) FROM runs r WHERE r.kind='scan' AND r.source_id=e.source_id)"
        values.append(request.max_bytes)
        # Interleave strata, then reproducibly choose entries within each stratum.
        order = "id"
        base = f"SELECT e.id,e.revision,e.size_bytes FROM entries e WHERE {where}"
        if not request.sample:
            base += " ORDER BY e.id LIMIT ?"
            values.append(request.max_files)
        if request.sample:
            base = f"""SELECT e.id,e.revision,e.size_bytes,
              row_number() OVER(PARTITION BY e.source_id,e.parent,e.suffix,
                CASE WHEN e.size_bytes<1048576 THEN 0 WHEN e.size_bytes<104857600 THEN 1 ELSE 2 END,
                CAST(e.mtime_ns/31557600000000000 AS INTEGER)
                ORDER BY sample_key(?,e.id)) AS sample_rank,
              sample_key(?,e.id) AS random_order FROM entries e WHERE {where}"""
            values = [request.seed, request.seed, *values]
            base = f"SELECT * FROM ({base}) WHERE sample_rank<=?"
            values.append(request.per_stratum)
            order = "sample_rank,random_order,id"
        # Running sum enforces the byte budget without materializing members in Python.
        query = f"""WITH candidates AS ({base}), bounded AS (
          SELECT id,revision,sum(size_bytes) OVER(ORDER BY {order}) AS running_bytes,
          row_number() OVER(ORDER BY {order}) AS position FROM candidates)
          SELECT ?,id,revision FROM bounded WHERE position<=? AND running_bytes<=?"""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            incomplete = conn.execute(
                "SELECT 1 FROM runs r WHERE kind='scan' AND id=(SELECT max(id) FROM runs x WHERE x.source_id=r.source_id AND x.kind='scan') AND status!='done'"
                + (" AND source_id=?" if request.filters.source_id is not None else ""),
                [request.filters.source_id]
                if request.filters.source_id is not None
                else [],
            ).fetchone()
            if incomplete and not request.allow_partial:
                raise ValueError(
                    "Discovery coverage is incomplete. Wait for completion or explicitly allow a partial selection."
                )
            now = time.time()
            sid = conn.execute(
                "INSERT INTO selections(request,created) VALUES(?,?)",
                (encode(request.model_dump()), now),
            ).lastrowid
            conn.execute(
                "INSERT INTO selection_members(selection_id,entry_id,revision) "
                + query,
                [*values, sid, request.max_files, request.max_bytes],
            )
            conn.execute(
                """UPDATE selection_members SET
              source_id=(SELECT source_id FROM entries WHERE id=entry_id),
              path=(SELECT path FROM entries WHERE id=entry_id),
              size_bytes=(SELECT size_bytes FROM entries WHERE id=entry_id),
              mtime_ns=(SELECT mtime_ns FROM entries WHERE id=entry_id),
              ctime_ns=(SELECT ctime_ns FROM entries WHERE id=entry_id),
              source_generation=(SELECT s.generation FROM entries e JOIN sources s ON s.id=e.source_id WHERE e.id=entry_id),
              file_device=(SELECT device FROM entries WHERE id=entry_id),
              file_inode=(SELECT inode FROM entries WHERE id=entry_id)
              WHERE selection_id=?""",
                (sid,),
            )
            conn.execute(
                "UPDATE selections SET count=(SELECT count(*) FROM selection_members WHERE selection_id=?),bytes=(SELECT coalesce(sum(e.size_bytes),0) FROM selection_members m JOIN entries e ON e.id=m.entry_id WHERE m.selection_id=?) WHERE id=?",
                (sid, sid, sid),
            )
            coverage = [
                dict(r)
                for r in conn.execute(
                    "SELECT id,source_id,status,payload,updated FROM runs r WHERE kind='scan' AND id=(SELECT max(id) FROM runs x WHERE x.source_id=r.source_id AND x.kind='scan')"
                    + (
                        " AND source_id=?"
                        if request.filters.source_id is not None
                        else ""
                    ),
                    [request.filters.source_id]
                    if request.filters.source_id is not None
                    else [],
                )
            ]
            conn.execute(
                "UPDATE selections SET coverage=? WHERE id=?", (encode(coverage), sid)
            )
            return dict(
                conn.execute("SELECT * FROM selections WHERE id=?", (sid,)).fetchone()
            )

    def selections(self, after: int = 0, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM selections WHERE id>? ORDER BY id LIMIT ?",
                    (after, limit),
                )
            ]

    def selection(self, selection_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM selections WHERE id=?", (selection_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Selection not found")
            return dict(row)

    def staged_members(self, selection_id: int) -> list[dict]:
        """Read a bounded immutable snapshot, never expand a source directory."""
        selection = self.selection(selection_id)
        if not 0 < selection["count"] <= 10_000:
            raise ValueError(
                "Intake requires between 1 and 10,000 frozen files; select a smaller batch"
            )
        with self.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """SELECT m.*,s.root,s.device,s.inode,
                s.generation,e.revision AS current_revision,e.status,e.metadata_state,
                EXISTS(SELECT 1 FROM sidecar_links l WHERE l.entry_id=e.id AND l.revision=m.revision) AS sidecar_processed
                FROM selection_members m JOIN sources s ON s.id=m.source_id
                JOIN entries e ON e.id=m.entry_id WHERE selection_id=? ORDER BY entry_id LIMIT 10001""",
                    (selection_id,),
                )
            ]
        if len(rows) != selection["count"] or any(
            row["size_bytes"] is None for row in rows
        ):
            raise ValueError("Selection has incomplete metadata; scan and select again")
        if any(
            row["revision"] != row["current_revision"]
            or row["status"] != "present"
            or row["metadata_state"] != "known"
            or row["source_generation"] != row["generation"]
            for row in rows
        ):
            raise ValueError("Selection is stale; scan and select again")
        return rows

    def handoff(self, selection_id: int, settings: dict) -> str:
        key = hashlib.sha256(encode(settings).encode()).hexdigest()
        run_id = hashlib.sha256(
            f"{self.path}:{selection_id}:{key}".encode()
        ).hexdigest()[:32]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO intake_handoffs VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                (selection_id, key, run_id, time.time()),
            )
            return conn.execute(
                "SELECT run_id FROM intake_handoffs WHERE selection_id=? AND request_key=?",
                (selection_id, key),
            ).fetchone()[0]

    def link_sidecar(self, member: dict, file_id: str, run_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sidecar_links VALUES(?,?,?,?,?) ON CONFLICT(entry_id,revision) DO UPDATE SET file_id=excluded.file_id,run_id=excluded.run_id,updated=excluded.updated",
                (member["entry_id"], member["revision"], file_id, run_id, time.time()),
            )

    def selection_entries(
        self, selection_id: int, after: int = 0, limit: int = 100
    ) -> dict:
        with self.connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT e.*,m.path AS selected_path,m.size_bytes AS selected_size,m.mtime_ns AS selected_mtime,m.revision AS selected_revision,e.revision!=m.revision OR e.status!='present' AS stale FROM selection_members m JOIN entries e ON e.id=m.entry_id WHERE m.selection_id=? AND e.id>? ORDER BY e.id LIMIT ?",
                    (selection_id, after, limit + 1),
                )
            ]
        for row in rows:
            row.update(
                path=row.pop("selected_path"),
                size_bytes=row.pop("selected_size"),
                mtime_ns=row.pop("selected_mtime"),
            )
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def new_processing(self, request: ProcessRequest) -> int:
        with self.connect() as conn:
            selection = conn.execute(
                "SELECT * FROM selections WHERE id=?", (request.selection_id,)
            ).fetchone()
            if not selection:
                raise KeyError("Selection not found")
            if not selection["count"]:
                raise ValueError("Selection is empty")
            now = time.time()
            rid = conn.execute(
                "INSERT INTO runs(kind,selection_id,payload,created,updated) VALUES(?,?,?,?,?)",
                (
                    request.stage,
                    request.selection_id,
                    encode(request.model_dump()),
                    now,
                    now,
                ),
            ).lastrowid
            conn.execute(
                "INSERT INTO work_items(run_id,entry_id,revision) SELECT ?,entry_id,revision FROM selection_members WHERE selection_id=?",
                (rid, request.selection_id),
            )
            return rid

    def run(self, run_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError("Run not found")
            result = dict(row)
            if result["kind"] == "scan":
                result["directories"] = {
                    r["status"]: r["count"]
                    for r in conn.execute(
                        "SELECT status,count(*) AS count FROM directories WHERE run_id=? GROUP BY status",
                        (run_id,),
                    )
                }
                result["current_paths"] = [
                    r[0]
                    for r in conn.execute(
                        "SELECT path FROM directories WHERE run_id=? AND status='running' LIMIT 8",
                        (run_id,),
                    )
                ]
            result["items"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT status,count(*) AS count,sum(seconds) AS seconds,sum(bytes) AS bytes,sum(text_chars) AS text_chars FROM work_items WHERE run_id=? GROUP BY status",
                    (run_id,),
                )
            ]
            return result

    def runs(self, after: int = 0, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM runs WHERE id>? ORDER BY id LIMIT ?", (after, limit)
                )
            ]

    def control(self, run_id: int, action: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise KeyError("Run not found")
            state = row["status"]
            if action == "pause" and state in {"running", "queued"}:
                conn.execute(
                    "UPDATE runs SET status='paused',updated=? WHERE id=?",
                    (time.time(), run_id),
                )
            elif action == "cancel" and state in {"running", "queued", "paused"}:
                conn.execute(
                    "UPDATE runs SET status='cancelled',updated=? WHERE id=?",
                    (time.time(), run_id),
                )
            elif action == "resume" and state in {"paused", "error"}:
                scan = conn.execute(
                    "SELECT kind,source_id FROM runs WHERE id=?", (run_id,)
                ).fetchone()
                if (
                    scan["kind"] == "scan"
                    and conn.execute(
                        "SELECT 1 FROM runs WHERE kind='scan' AND source_id=? AND id>?",
                        (scan["source_id"], run_id),
                    ).fetchone()
                ):
                    raise ValueError(
                        "A newer scan superseded this one; resume the latest scan or start a fresh scan"
                    )
                # Do not release an in-flight worker's lease. It will exit at its next boundary.
                conn.execute(
                    "UPDATE runs SET status='queued',error=NULL,updated=? WHERE id=?",
                    (time.time(), run_id),
                )
                conn.execute(
                    "UPDATE directories SET status='pending',error=NULL,attempts=0 WHERE run_id=? AND status='error'",
                    (run_id,),
                )
                conn.execute(
                    "UPDATE work_items SET status='pending',error=NULL,attempts=0 WHERE run_id=? AND status='error'",
                    (run_id,),
                )
            else:
                raise ValueError(f"Cannot {action} a {state} run")
        return self.run(run_id)

    def claim(self, owner: str) -> dict | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = time.time()
            # Exactly one active coordinator across scanner/processor processes.
            if conn.execute(
                "SELECT 1 FROM runs WHERE owner IS NOT NULL AND lease_until>?", (now,)
            ).fetchone():
                return None
            conn.execute(
                "UPDATE runs SET status=CASE WHEN status='running' THEN 'queued' ELSE status END,owner=NULL,lease_until=NULL WHERE owner IS NOT NULL AND lease_until<=?",
                (now,),
            )
            row = conn.execute(
                "SELECT * FROM runs WHERE status='queued' AND owner IS NULL ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            rid = row["id"]
            conn.execute(
                "UPDATE runs SET status='running',owner=?,lease_until=?,updated=? WHERE id=?",
                (owner, now + 60, now, rid),
            )
            conn.execute(
                "UPDATE directories SET status='pending' WHERE run_id=? AND status='running'",
                (rid,),
            )
            conn.execute(
                "UPDATE work_items SET status='pending' WHERE run_id=? AND status='running'",
                (rid,),
            )
            conn.execute(
                "UPDATE work_items SET status='error',error='Worker recovery exhausted after three attempts' WHERE run_id=? AND status='pending' AND attempts>=3",
                (rid,),
            )
            return dict(
                conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
            )

    def heartbeat(self, run_id: int, owner: str) -> bool:
        with self.connect() as conn:
            return bool(
                conn.execute(
                    "UPDATE runs SET lease_until=? WHERE id=? AND owner=? AND lease_until>?",
                    (time.time() + 60, run_id, owner, time.time()),
                ).rowcount
            )

    def owned(self, conn: sqlite3.Connection, run_id: int, owner: str) -> bool:
        return bool(
            conn.execute(
                "SELECT 1 FROM runs WHERE id=? AND owner=? AND lease_until>? AND status='running'",
                (run_id, owner, time.time()),
            ).fetchone()
        )

    def events(self, run_id: int, after: int = 0, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT ?",
                    (run_id, after, limit),
                )
            ]

    def search(self, query: str, after: int = 0, limit: int = 50) -> dict:
        with self.connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    """SELECT e.id,e.source_id,e.path,e.revision,e.extraction_id,
              snippet(text_search,0,'[',']',' … ',32) AS snippet
              FROM entries e JOIN extractions x ON x.id=e.extraction_id
              JOIN text_search ON text_search.rowid=x.rowid
              WHERE text_search MATCH ? AND e.status='present' AND e.id>?
              ORDER BY e.id LIMIT ?""",
                    (query, after, limit + 1),
                )
            ]
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    def document(self, entry_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT e.*,x.response,x.text,x.sha256 FROM entries e LEFT JOIN extractions x ON x.id=e.extraction_id WHERE e.id=?",
                (entry_id,),
            ).fetchone()
            if not row:
                raise KeyError("Entry not found")
            result = dict(row)
            result["products"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT p.id,p.run_id,p.kind,p.created,p.extraction_id,p.extraction_id IS NOT e.extraction_id OR e.status!='present' AS stale FROM products p JOIN entries e ON e.id=p.entry_id WHERE p.entry_id=? ORDER BY p.id DESC LIMIT 20",
                    (entry_id,),
                )
            ]
            result["history"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT revision,extraction_id FROM entry_extractions WHERE entry_id=? ORDER BY revision DESC LIMIT 20",
                    (entry_id,),
                )
            ]
            return result

    def product(self, product_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT p.*,e.path,p.extraction_id IS NOT e.extraction_id OR e.status!='present' AS stale FROM products p JOIN entries e ON e.id=p.entry_id WHERE p.id=?",
                (product_id,),
            ).fetchone()
            if not row:
                raise KeyError("Product not found")
            return dict(row)

    def extraction(self, entry_id: int, extraction_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT x.*,h.revision,e.path,e.source_id FROM extractions x JOIN entry_extractions h ON h.extraction_id=x.id JOIN entries e ON e.id=h.entry_id WHERE h.entry_id=? AND x.id=? ORDER BY h.revision DESC LIMIT 1",
                (entry_id, extraction_id),
            ).fetchone()
            if not row:
                raise KeyError("Extraction not found for this source entry")
            return dict(row)

    def report(self, run_id: int) -> dict:
        run = self.run(run_id)
        with self.connect() as conn:
            selection = conn.execute(
                "SELECT * FROM selections WHERE id=?", (run["selection_id"],)
            ).fetchone()
            if not selection:
                raise ValueError("Reports apply to processing runs")
            request = SelectionRequest.model_validate_json(selection["request"])
            strata = [
                dict(row)
                for row in conn.execute(
                    """SELECT e.suffix,
              CASE WHEN e.size_bytes<1048576 THEN 'under 1 MiB' WHEN e.size_bytes<104857600 THEN '1–100 MiB' ELSE '100 MiB or more' END AS size_group,
              w.status,count(*) AS files,sum(w.seconds) AS seconds,sum(w.bytes) AS bytes,
              sum(w.text_chars) AS text_chars FROM work_items w JOIN entries e ON e.id=w.entry_id
              WHERE w.run_id=? GROUP BY e.suffix,size_group,w.status""",
                    (run_id,),
                )
            ]
            stats = dict(
                conn.execute(
                    """SELECT count(*) AS attempted,
              coalesce(sum(status IN ('done','reused')),0) AS usable,
              coalesce(sum(status='needs_ocr'),0) AS needs_ocr,
              coalesce(sum(status='reused'),0) AS reused,
              coalesce(sum(status='error'),0) AS errors,
              coalesce(sum(text_chars),0) AS text_chars,
              coalesce(sum(seconds),0) AS seconds FROM work_items
              WHERE run_id=? AND status NOT IN ('pending','running')""",
                    (run_id,),
                ).fetchone()
            )
        target = self.summary(request.filters)
        fraction = stats["attempted"] / selection["count"] if selection["count"] else 0
        return {
            "run": run,
            "selection": dict(selection),
            "strata": strata,
            "metrics": stats,
            "selection_coverage": fraction,
            "current_matching_inventory": target["files"],
            "estimated_seconds_for_matching_files": stats["seconds"]
            / stats["attempted"]
            * target["files"]
            if stats["attempted"]
            else None,
            "estimate_note": "Heuristic extrapolation from the selected sample, not a confidence interval or cost guarantee. Folder/format mix, caching, OCR, and share latency may differ; reused results lower observed time.",
        }

    def backup(self, destination: Path) -> None:
        destination = destination.expanduser().resolve()
        if destination.exists():
            raise ValueError("Backup destination already exists")
        for source in self.sources():
            if destination.is_relative_to(Path(source["root"])):
                raise ValueError("Backups must be outside source roots")
        target = sqlite3.connect(destination)
        try:
            with self.connect() as conn:
                conn.backup(target, pages=512)
        finally:
            target.close()
        destination.chmod(0o600)

    def rebuild_search(self) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO text_search(text_search) VALUES('rebuild')")
