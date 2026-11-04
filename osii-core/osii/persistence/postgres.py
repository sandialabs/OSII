"""PostgreSQL is authoritative. No file-store or SQLite fallback."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Iterator
import uuid

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        LargeBinary, MetaData, String, Table, Text, create_engine,
                        delete, insert, select, text, update)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection


metadata = MetaData()
datasets = Table("datasets", metadata, Column("id", String, primary_key=True),
                 Column("revision", Integer, nullable=False, default=0))
documents = Table("documents", metadata,
    Column("file_id", String, primary_key=True), Column("source_relpath", Text, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("sha256", String, nullable=False), Column("filename", Text, nullable=False),
    Column("media_type", String, nullable=False), Column("size_bytes", Integer, nullable=False),
    Column("text", Text, nullable=False), Column("metadata", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False))
extractions = Table("extractions", metadata, Column("id", String, primary_key=True),
    Column("file_id", String, ForeignKey("documents.file_id", ondelete="CASCADE"), nullable=False),
    Column("sha256", String, nullable=False), Column("response", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False))
chunks = Table("chunks", metadata, Column("chunk_id", String, primary_key=True),
    Column("file_id", String, ForeignKey("documents.file_id", ondelete="CASCADE"), nullable=False, index=True),
    Column("text", Text, nullable=False), Column("char_start", Integer, nullable=False),
    Column("char_end", Integer, nullable=False), Column("source_origin", JSONB, nullable=False),
    Column("embedding", JSONB), Column("embedding_model", String))
artifacts = Table("artifacts", metadata, Column("id", String, primary_key=True),
    Column("file_id", String, ForeignKey("documents.file_id", ondelete="CASCADE"), nullable=False),
    Column("kind", String, nullable=False), Column("payload", JSONB, nullable=False))
collections = Table("collections", metadata, Column("id", String, primary_key=True),
    Column("name", String, unique=True, nullable=False), Column("description", Text, nullable=False),
    Column("members", JSONB, nullable=False))
settings = Table("settings", metadata, Column("id", String, primary_key=True),
    Column("value", JSONB, nullable=False))
jobs = Table("jobs", metadata, Column("id", String, primary_key=True),
    Column("status", String, nullable=False, index=True), Column("kind", String, nullable=False),
    Column("payload", JSONB, nullable=False), Column("logs", JSONB, nullable=False),
    Column("attempts", Integer, nullable=False), Column("worker_id", String),
    Column("lease_until", DateTime(timezone=True)), Column("created_at", DateTime(timezone=True), nullable=False))
users = Table("users", metadata, Column("id", String, primary_key=True),
    Column("username", String, unique=True, nullable=False), Column("password_hash", Text, nullable=False),
    Column("role", String, nullable=False), Column("active", Boolean, nullable=False),
    Column("must_change_password", Boolean, nullable=False), Column("auth_version", Integer, nullable=False))
identities = Table("identities", metadata, Column("id", String, primary_key=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("provider", String, nullable=False), Column("subject", String, nullable=False, unique=True))
sessions = Table("sessions", metadata, Column("token_hash", String, primary_key=True),
    Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("csrf_hash", String, nullable=False), Column("auth_version", Integer, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False), Column("last_seen", DateTime(timezone=True), nullable=False))
attempts = Table("login_attempts", metadata, Column("id", String, primary_key=True),
    Column("count", Integer, nullable=False), Column("expires_at", DateTime(timezone=True), nullable=False))
audit = Table("audit", metadata, Column("id", String, primary_key=True),
    Column("actor", String), Column("event", String, nullable=False), Column("resource", String),
    Column("created_at", DateTime(timezone=True), nullable=False))


def now() -> datetime:
    return datetime.now(timezone.utc)


def identifier() -> str:
    return str(uuid.uuid4())


class PostgresStore:
    def __init__(self, url: str):
        if not url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        self.engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1), pool_pre_ping=True)

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def ready(self) -> None:
        with self.engine.connect() as c:
            if c.execute(text("SELECT version_num FROM alembic_version")).scalar() != "0001_server":
                raise RuntimeError("Run the explicit database migration before starting OSII-server")

    def record(self, event: str, actor: str | None = None, resource: str | None = None) -> None:
        with self.transaction() as c:
            c.execute(insert(audit).values(id=identifier(), actor=actor, event=event, resource=resource, created_at=now()))

    def account(self, *, username: str | None = None, user_id: str | None = None) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(select(users).where(users.c.username == username if username is not None else users.c.id == user_id)).mappings().first()
            return dict(row) if row else None

    def list_accounts(self) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(users).order_by(users.c.username)).mappings()]

    def create_account(self, username: str, password_hash: str, role: str, *, bootstrap: bool = False) -> str:
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914034)"))
            if bootstrap and c.execute(select(users.c.id).limit(1)).first():
                raise ValueError("Bootstrap is only allowed for an empty account database")
            uid = identifier()
            c.execute(insert(users).values(id=uid, username=username, password_hash=password_hash, role=role,
                active=True, must_change_password=not bootstrap, auth_version=0))
            return uid

    def change_account(self, uid: str, changes: dict) -> None:
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914034)"))
            current = c.execute(select(users).where(users.c.id == uid).with_for_update()).mappings().first()
            if not current:
                raise ValueError("Account not found")
            if current["role"] == "admin" and current["active"] and (changes.get("role", "admin") != "admin" or changes.get("active") is False):
                others = c.execute(select(users.c.id).where(users.c.role == "admin", users.c.active, users.c.id != uid)).first()
                if not others:
                    raise ValueError("Cannot remove the last active administrator")
            c.execute(update(users).where(users.c.id == uid).values(**changes, auth_version=users.c.auth_version + 1))
            c.execute(delete(sessions).where(sessions.c.user_id == uid))

    def login_allowed(self, key: str, failed: bool = False, *, maximum: int = 10, seconds: int = 900) -> bool:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)})
            row = c.execute(select(attempts).where(attempts.c.id == key).with_for_update()).mappings().first()
            count = row["count"] if row and row["expires_at"] > now() else 0
            if failed:
                statement = upsert(attempts).values(id=key, count=count + 1,
                    expires_at=row["expires_at"] if count else now() + timedelta(seconds=seconds))
                c.execute(statement.on_conflict_do_update(index_elements=[attempts.c.id], set_={"count": statement.excluded.count, "expires_at": statement.excluded.expires_at}))
            return count < maximum

    def create_session(self, uid: str, token_hash: str, csrf_hash: str, version: int) -> None:
        with self.transaction() as c:
            c.execute(insert(sessions).values(token_hash=token_hash, user_id=uid, csrf_hash=csrf_hash,
                auth_version=version, expires_at=now() + timedelta(hours=12), last_seen=now()))

    def session(self, token_hash: str) -> dict | None:
        with self.transaction() as c:
            row = c.execute(select(sessions, users).join(users, users.c.id == sessions.c.user_id).where(
                sessions.c.token_hash == token_hash, sessions.c.expires_at > now(),
                sessions.c.last_seen > now() - timedelta(minutes=30), users.c.active,
                sessions.c.auth_version == users.c.auth_version)).mappings().first()
            if not row:
                return None
            c.execute(update(sessions).where(sessions.c.token_hash == token_hash).values(last_seen=now()))
            return dict(row)

    def delete_session(self, token_hash: str) -> None:
        with self.transaction() as c:
            c.execute(delete(sessions).where(sessions.c.token_hash == token_hash))

    def configuration(self) -> dict:
        with self.engine.connect() as c:
            return c.execute(select(settings.c.value).where(settings.c.id == "models")).scalar() or {
                "chat_model": "", "embedding_model": ""}

    def save_configuration(self, value: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            s = upsert(settings).values(id="models", value=value)
            c.execute(s.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": value}))

    def snapshot(self) -> tuple[int, list[dict], list[dict]]:
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            with c.begin():
                revision = c.execute(select(datasets.c.revision).where(datasets.c.id == "shared")).scalar() or 0
                docs = [dict(row) for row in c.execute(select(documents).where(documents.c.active)).mappings()]
                rows = [dict(row) for row in c.execute(select(chunks, documents.c.filename, documents.c.source_relpath)
                    .join(documents, documents.c.file_id == chunks.c.file_id).where(documents.c.active)).mappings()]
                return revision, docs, rows

    def document(self, file_id: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(select(documents).where(documents.c.file_id == file_id)).mappings().first()
            return dict(row) if row else None

    def commit_document(self, document: dict, chunk_rows: list[dict], extraction: dict, artifact_rows: list[dict]) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        document = {**document, "active": True}
        with self.transaction() as c:
            c.execute(update(documents).where(documents.c.source_relpath == document["source_relpath"],
                documents.c.file_id != document["file_id"]).values(active=False))
            s = upsert(documents).values(**document, updated_at=now())
            c.execute(s.on_conflict_do_update(index_elements=[documents.c.file_id], set_={
                **document, "updated_at": now()}))
            c.execute(delete(chunks).where(chunks.c.file_id == document["file_id"]))
            if chunk_rows:
                c.execute(insert(chunks), chunk_rows)
            c.execute(insert(extractions).values(id=identifier(), file_id=document["file_id"],
                sha256=document["sha256"], response=extraction, created_at=now()))
            c.execute(delete(artifacts).where(artifacts.c.file_id == document["file_id"]))
            if artifact_rows:
                c.execute(insert(artifacts), artifact_rows)
            c.execute(update(datasets).where(datasets.c.id == "shared").values(revision=datasets.c.revision + 1))

    def list_artifacts(self, file_id: str) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(artifacts).where(artifacts.c.file_id == file_id)).mappings()]

    def collection_records(self) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(collections).order_by(collections.c.name)).mappings()]

    def save_collection(self, value: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            s = upsert(collections).values(**value)
            c.execute(s.on_conflict_do_update(index_elements=[collections.c.id], set_=value))

    def enqueue(self, kind: str, payload: dict) -> str:
        with self.transaction() as c:
            jid = identifier()
            c.execute(insert(jobs).values(id=jid, kind=kind, status="queued", payload=payload,
                logs=[], attempts=0, created_at=now()))
            return jid

    def job_records(self) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(jobs).order_by(jobs.c.created_at.desc()).limit(100)).mappings()]

    def claim(self, worker: str) -> dict | None:
        with self.transaction() as c:
            # Expired leases are recoverable; repeated failure is bounded.
            c.execute(update(jobs).where(jobs.c.status == "running", jobs.c.lease_until < now()).values(status="queued"))
            c.execute(update(jobs).where(jobs.c.status == "queued", jobs.c.attempts >= 3)
                .values(status="error", logs=["Worker recovery exhausted after three attempts."]))
            row = c.execute(select(jobs).where(jobs.c.status == "queued", jobs.c.attempts < 3)
                .order_by(jobs.c.created_at).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not row:
                return None
            c.execute(update(jobs).where(jobs.c.id == row["id"]).values(status="running", worker_id=worker,
                lease_until=now() + timedelta(minutes=5), attempts=jobs.c.attempts + 1))
            return dict(row)

    def heartbeat(self, jid: str, worker: str) -> None:
        with self.transaction() as c:
            c.execute(update(jobs).where(jobs.c.id == jid, jobs.c.worker_id == worker, jobs.c.status == "running")
                .values(lease_until=now() + timedelta(minutes=5)))

    def finish(self, jid: str, worker: str, logs: list[str], failed: bool = False) -> None:
        with self.transaction() as c:
            c.execute(update(jobs).where(jobs.c.id == jid, jobs.c.worker_id == worker)
                .values(status="error" if failed else "done", logs=logs, lease_until=None))
