"""PostgreSQL is authoritative. No file-store or SQLite fallback."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Iterator
from collections.abc import Callable
import uuid

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        LargeBinary, MetaData, String, Table, Text, create_engine,
                        delete, insert, select, text, update, or_, func, UniqueConstraint, case)
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
    Column("name", String, nullable=False), Column("description", Text, nullable=False),
    Column("members", JSONB, nullable=False),
    Column("owner_id", String, ForeignKey("users.id", ondelete="SET NULL")),
    Column("visibility", String, nullable=False, server_default="private"),
    UniqueConstraint("owner_id", "name", name="collections_owner_name_key"))
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
    Column("expires_at", DateTime(timezone=True), nullable=False), Column("last_seen", DateTime(timezone=True), nullable=False),
    Column("idle_seconds", Integer, nullable=False, server_default="1800"))
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
            if c.execute(text("SELECT version_num FROM alembic_version")).scalar() != "0003_session_policy":
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

    def create_session(self, uid: str, token_hash: str, csrf_hash: str, version: int, *,
                       lifetime_seconds: int = 43200, idle_seconds: int = 1800) -> None:
        with self.transaction() as c:
            c.execute(insert(sessions).values(token_hash=token_hash, user_id=uid, csrf_hash=csrf_hash,
                auth_version=version, expires_at=now() + timedelta(seconds=lifetime_seconds),
                last_seen=now(), idle_seconds=idle_seconds))

    def session(self, token_hash: str) -> dict | None:
        with self.transaction() as c:
            row = c.execute(select(sessions, users).join(users, users.c.id == sessions.c.user_id).where(
                sessions.c.token_hash == token_hash, sessions.c.expires_at > now(),
                users.c.active,
                sessions.c.auth_version == users.c.auth_version)).mappings().first()
            if not row or row["last_seen"] <= now() - timedelta(seconds=row["idle_seconds"]):
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

    def assert_models_idle(self, connection: Connection) -> None:
        if connection.execute(select(jobs.c.id).where(jobs.c.status.in_(["queued", "running", "pausing", "cancelling"])).limit(1)).first():
            raise ValueError("Wait for processing jobs to finish before changing models or endpoints")

    def save_configuration(self, value: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914036)"))
            self.assert_models_idle(c)
            s = upsert(settings).values(id="models", value=value)
            c.execute(s.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": value}))

    def save_model_connection(self, kind: str, record: dict | None, *, model: str | None = None,
                              model_name: str = "") -> None:
        """Keep endpoint credentials and their selected model in one transaction."""
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914036)"))
            self.assert_models_idle(c)
            endpoints = dict(c.execute(select(settings.c.value).where(settings.c.id == "model_endpoints")).scalar() or {})
            if record is None:
                endpoints.pop(kind, None)
            else:
                endpoints[kind] = record
            changes = {"model_endpoints": endpoints}
            if kind in {"chat", "embedding"} and model is not None:
                choices = dict(c.execute(select(settings.c.value).where(settings.c.id == "models")).scalar() or {
                    "chat_model": "", "embedding_model": ""})
                choices.update({kind + "_model": model, kind + "_model_name": model_name or model})
                changes["models"] = choices
            for key, value in changes.items():
                statement = upsert(settings).values(id=key, value=value)
                c.execute(statement.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": value}))

    def snapshot(self) -> tuple[int, list[dict], list[dict]]:
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            with c.begin():
                revision = c.execute(select(datasets.c.revision).where(datasets.c.id == "shared")).scalar() or 0
                docs = [dict(row) for row in c.execute(select(documents).where(documents.c.active)).mappings()]
                from array import array
                rows = []
                result = c.execution_options(stream_results=True, max_row_buffer=16).execute(select(chunks, documents.c.filename, documents.c.source_relpath)
                    .join(documents, documents.c.file_id == chunks.c.file_id).where(documents.c.active))
                for row in result.mappings():
                    value = dict(row)
                    if isinstance(value.get('embedding'), list):
                        # Retrieval already uses float32. Keep the canonical JSONB
                        # unchanged while avoiding millions of boxed Python floats.
                        value['embedding'] = array('f', value['embedding'])
                    rows.append(value)
                result.close()
                return revision, docs, rows

    def document(self, file_id: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(select(documents).where(documents.c.file_id == file_id)).mappings().first()
            return dict(row) if row else None

    def commit_document(self, document: dict, chunk_rows: list[dict], extraction: dict, artifact_rows: list[dict], *, job_owner: tuple[str, str] | None = None) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        extraction_id = identifier()
        document = {**document, "active": True, "metadata": {**document["metadata"], "primary_extraction_id": extraction_id}}
        with self.transaction() as c:
            self.assert_job_owner(c, job_owner)
            c.execute(update(documents).where(documents.c.source_relpath == document["source_relpath"],
                documents.c.file_id != document["file_id"]).values(active=False))
            s = upsert(documents).values(**document, updated_at=now())
            c.execute(s.on_conflict_do_update(index_elements=[documents.c.file_id], set_={
                **document, "updated_at": now()}))
            c.execute(delete(chunks).where(chunks.c.file_id == document["file_id"]))
            if chunk_rows:
                c.execute(insert(chunks), chunk_rows)
            c.execute(insert(extractions).values(id=extraction_id, file_id=document["file_id"],
                sha256=document["sha256"], response=extraction, created_at=now()))
            c.execute(delete(artifacts).where(artifacts.c.file_id == document["file_id"], artifacts.c.kind.not_in(["manual_metadata", "manual_metadata_history"]), or_(artifacts.c.kind.not_in(["synthesis", "enrichment"]), artifacts.c.payload["input_extraction_id"].astext.is_(None))))
            if artifact_rows:
                c.execute(insert(artifacts), artifact_rows)
            c.execute(update(datasets).where(datasets.c.id == "shared").values(revision=datasets.c.revision + 1))

    def list_artifacts(self, file_id: str) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(artifacts).where(artifacts.c.file_id == file_id)).mappings()]

    def collection_records(self, user_id: str | None = None) -> list[dict]:
        visible = collections.c.visibility == "shared"
        if user_id:
            visible = or_(visible, collections.c.owner_id == user_id)
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(collections).where(visible).order_by(collections.c.name)).mappings()]

    @staticmethod
    def _collection_version(previous: dict):
        return [collections.c[key] == previous[key] for key in
            ("id", "owner_id", "visibility", "name", "description", "members")]

    def delete_collection(self, previous: dict) -> bool:
        with self.transaction() as c:
            return c.execute(delete(collections).where(*self._collection_version(previous))).rowcount == 1

    def setting(self, key: str, default: dict) -> dict:
        with self.engine.connect() as c:
            return c.execute(select(settings.c.value).where(settings.c.id == key)).scalar() or default

    def save_setting(self, key: str, value: dict) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            statement = upsert(settings).values(id=key, value=value)
            c.execute(statement.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": value}))

    def statistics(self) -> dict:
        model = self.configuration().get("embedding_model", "")
        nonempty = case((func.jsonb_typeof(chunks.c.embedding) == "array", func.jsonb_array_length(chunks.c.embedding) > 0), else_=False)
        compatible = func.coalesce((chunks.c.embedding_model == model) & nonempty, False)
        coverage = select(chunks.c.file_id).group_by(chunks.c.file_id).having(func.bool_and(compatible)).subquery()
        with self.engine.connect() as c:
            return {"documents": c.execute(select(func.count()).select_from(documents).where(documents.c.active)).scalar(),
                "text_documents": c.execute(select(func.count()).select_from(documents).where(documents.c.active, func.length(func.trim(documents.c.text)) > 0)).scalar(),
                "indexed_documents": c.execute(select(func.count()).select_from(documents.join(coverage, documents.c.file_id == coverage.c.file_id)).where(documents.c.active)).scalar() if model else 0,
                "chunks": c.execute(select(func.count()).select_from(chunks.join(documents)).where(documents.c.active)).scalar(),
                "embedded_chunks": c.execute(select(func.count()).select_from(chunks.join(documents)).where(documents.c.active, func.jsonb_typeof(chunks.c.embedding) == "array")).scalar()}


    def save_collection(self, value: dict, previous: dict | None = None) -> bool:
        with self.transaction() as c:
            if previous is None:
                c.execute(insert(collections).values(**value))
                return True
            # A curator's stale shared edit must not republish a now-private collection.
            return c.execute(update(collections).where(*self._collection_version(previous)).values(**value)).rowcount == 1

    def enqueue(self, kind: str, payload: dict, *, status: str = "queued") -> str:
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914036)"))
            jid = identifier()
            c.execute(insert(jobs).values(id=jid, kind=kind, status=status, payload=payload,
                logs=[], attempts=0, created_at=now()))
            return jid

    def job_records(self) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(jobs).order_by(jobs.c.created_at.desc()).limit(100)).mappings()]

    def claim(self, worker: str) -> dict | None:
        with self.transaction() as c:
            # Expired leases are recoverable; repeated failure is bounded.
            c.execute(update(jobs).where(jobs.c.status.in_(["running", "pausing", "cancelling"]), jobs.c.lease_until < now()).values(
                status=case((jobs.c.status == "pausing", "paused"),
                    (jobs.c.status == "cancelling", "cancelled"), else_="queued"), worker_id=None, lease_until=None))
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
            c.execute(update(jobs).where(jobs.c.id == jid, jobs.c.worker_id == worker, jobs.c.status.in_(["running", "pausing", "cancelling"]))
                .values(lease_until=now() + timedelta(minutes=5)))

    def progress(self, jid: str, worker: str, entry: str) -> bool:
        with self.transaction() as c:
            result = c.execute(update(jobs).where(jobs.c.id == jid, jobs.c.worker_id == worker,
                jobs.c.status.in_(["running", "pausing", "cancelling"])).values(logs=jobs.c.logs + [entry]))
            return result.rowcount == 1

    def finish(self, jid: str, worker: str, logs: list[str], failed: bool = False) -> None:
        with self.transaction() as c:
            c.execute(update(jobs).where(jobs.c.id == jid, jobs.c.worker_id == worker,
                jobs.c.status.in_(["running", "pausing", "cancelling"])).values(
                    status=case((jobs.c.status == "pausing", "paused"), (jobs.c.status == "cancelling", "cancelled"),
                                else_="error" if failed else "done"),
                    logs=logs[-2000:], worker_id=None, lease_until=None))


    def job(self, jid: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(select(jobs).where(jobs.c.id == jid)).mappings().first()
            return dict(row) if row else None

    def control_job(self, jid: str, action: str, configuration_stamp: str | Callable[[], str]) -> dict:
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914036)"))
            configuration_stamp = configuration_stamp() if callable(configuration_stamp) else configuration_stamp
            row = c.execute(select(jobs).where(jobs.c.id == jid).with_for_update()).mappings().first()
            if not row:
                raise ValueError("Processing plan not found")
            state, payload = row["status"], dict(row["payload"])
            transitions = {
                "start": {"staged": "queued"},
                "pause": {"queued": "paused", "running": "pausing"},
                "resume": {"paused": "queued"},
                "cancel": {"staged": "cancelled", "queued": "cancelled", "paused": "cancelled", "running": "cancelling", "pausing": "cancelling"},
                "retry": {"error": "queued"},
            }
            target = transitions.get(action, {}).get(state)
            if not target:
                raise ValueError(f"Cannot {action} a {state} run")
            if target == "queued" and payload.get("configuration_stamp", configuration_stamp) != configuration_stamp:
                raise ValueError("Model or processor settings changed. Stage a new plan with the current settings.")
            if action == "retry":
                payload["items"] = [{**item, "status": "pending", "error": None, "started_at": None, "finished_at": None, "duration_seconds": None} if item["status"] == "error" else item for item in payload.get("items", [])]
            c.execute(update(jobs).where(jobs.c.id == jid).values(status=target, payload=payload,
                attempts=0 if target == "queued" else row["attempts"]))
            return {**dict(row), "status": target, "payload": payload}

    def checkpoint(self, jid: str, worker: str, *, item: dict | None = None, index: int | None = None) -> str:
        """Persist file progress and honor controls only at a file boundary."""
        with self.transaction() as c:
            row = c.execute(select(jobs).where(jobs.c.id == jid).with_for_update()).mappings().first()
            if not row or row["worker_id"] != worker or row["status"] not in {"running", "pausing", "cancelling"} or row["lease_until"] <= now():
                raise ValueError("Worker no longer owns this processing run")
            payload = dict(row["payload"])
            if item is not None:
                payload["items"][index] = item
            state = {"pausing": "paused", "cancelling": "cancelled"}.get(row["status"], row["status"])
            c.execute(update(jobs).where(jobs.c.id == jid).values(payload=payload, status=state,
                **({"worker_id": None, "lease_until": None, "logs": row["logs"] + [f"Run {state} at a file boundary."]} if state != "running" else {})))
            return state

    def extraction_records(self, file_id: str) -> list[dict]:
        with self.engine.connect() as c:
            rows = [dict(row) for row in c.execute(select(extractions).where(extractions.c.file_id == file_id)
                .order_by(extractions.c.created_at.desc(), extractions.c.id)).mappings()]
            meta = c.execute(select(documents.c.metadata).where(documents.c.file_id == file_id)).scalar() or {}
            primary = meta.get('primary_extraction_id')
            return sorted(rows, key=lambda row: row['id'] != primary) if primary else rows

    def replace_embeddings(self, file_id: str, rows: list[dict], model: str, *, job_owner: tuple[str, str] | None = None) -> None:
        with self.transaction() as c:
            self.assert_job_owner(c, job_owner)
            doc = c.execute(select(documents).where(documents.c.file_id == file_id).with_for_update()).mappings().one()
            for row in rows:
                c.execute(update(chunks).where(chunks.c.file_id == file_id, chunks.c.chunk_id == row["chunk_id"])
                    .values(embedding=row["embedding"], embedding_model=model))
            c.execute(update(documents).where(documents.c.file_id == file_id).values(
                metadata={**doc["metadata"], "embedding_model": model, "embedding_warning": ""}, updated_at=now()))
            c.execute(update(datasets).where(datasets.c.id == "shared").values(revision=datasets.c.revision + 1))

    def document_chunks(self, file_id: str) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(row) for row in c.execute(select(chunks).where(chunks.c.file_id == file_id).order_by(chunks.c.char_start)).mappings()]


    def indexed_paths(self) -> set[str]:
        with self.engine.connect() as c:
            return set(c.execute(select(documents.c.source_relpath).where(documents.c.active)).scalars())


    @staticmethod
    def assert_job_owner(connection: Connection, owner: tuple[str, str] | None) -> None:
        if owner is None:
            return
        jid, worker = owner
        row = connection.execute(select(jobs.c.id).where(jobs.c.id == jid, jobs.c.worker_id == worker,
            jobs.c.status.in_(["running", "pausing", "cancelling"]), jobs.c.lease_until > now()).with_for_update()).first()
        if not row:
            raise ValueError("Worker no longer owns this processing run; no document changes were committed")


    def delete_setting(self, key: str) -> None:
        with self.transaction() as c:
            c.execute(delete(settings).where(settings.c.id == key))

    def save_processor_urls(self, urls: list[str]) -> None:
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(914036)"))
            self.assert_models_idle(c)
            row = upsert(settings).values(id="processor_endpoints", value={"urls": urls})
            c.execute(row.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": row.excluded.value}))

    def processor_grant(self, key: str, *, capability: str | None = None, model: str = "", consume: bool = False) -> dict:
        with self.transaction() as c:
            row = c.execute(select(settings.c.value).where(settings.c.id == key).with_for_update()).scalar()
            if not row or datetime.fromisoformat(row["expires_at"]) <= now():
                raise ValueError("Processor model grant is missing or expired")
            self.assert_job_owner(c, (row["job_id"], row["worker"]))
            if capability and (not row["bindings"].get(capability) or row["bindings"][capability] != model):
                raise ValueError("Model is outside this processor grant")
            if consume:
                if row["remaining_calls"] <= 0:
                    raise ValueError("Processor model request budget exhausted")
                row = {**row, "remaining_calls": row["remaining_calls"]-1}
                c.execute(update(settings).where(settings.c.id == key).values(value=row))
            return row

    def commit_processing_output(self, file_id: str, kind: str, payload: dict, *, jid: str, worker: str, index: int, item: dict) -> str:
        from sqlalchemy.dialects.postgresql import insert as upsert
        output_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"osii:{jid}:{index}:{kind}"))
        with self.transaction() as c:
            self.assert_job_owner(c, (jid, worker))
            doc = c.execute(select(documents).where(documents.c.file_id == file_id, documents.c.active).with_for_update()).mappings().one()
            latest = c.execute(select(extractions.c.id).where(extractions.c.file_id == file_id).order_by(extractions.c.created_at.desc(), extractions.c.id).limit(1)).scalar()
            latest = doc["metadata"].get("primary_extraction_id") or latest
            if hashlib.sha256(doc["text"].encode()).hexdigest() != payload["input_text_sha256"] or latest != payload["input_extraction_id"]:
                raise ValueError("Primary text changed during processing; no derived output was committed")
            statement = upsert(artifacts).values(id=output_id, file_id=file_id, kind=kind, payload=payload)
            c.execute(statement.on_conflict_do_update(index_elements=[artifacts.c.id], set_={"payload": payload}))
            job = c.execute(select(jobs.c.payload).where(jobs.c.id == jid)).scalar()
            job["items"][index] = item
            c.execute(update(jobs).where(jobs.c.id == jid).values(payload=job))
        return output_id

    def processing_output(self, jid: str, index: int, kind: str) -> dict | None:
        output_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"osii:{jid}:{index}:{kind}"))
        with self.engine.connect() as c:
            value = c.execute(select(artifacts).where(artifacts.c.id == output_id)).mappings().first()
            return dict(value) if value else None

    def update_processing_item(self, jid: str, worker: str, index: int, item: dict) -> None:
        """Step progress within a file; pause/cancel still waits for its boundary."""
        with self.transaction() as c:
            self.assert_job_owner(c, (jid, worker))
            payload = c.execute(select(jobs.c.payload).where(jobs.c.id == jid)).scalar()
            payload['items'][index] = item
            c.execute(update(jobs).where(jobs.c.id == jid).values(payload=payload))


    def prune_processor_grants(self) -> None:
        with self.transaction() as c:
            c.execute(delete(settings).where(settings.c.id.like('processor_grant:%'),
                settings.c.value['expires_at'].astext.cast(DateTime(timezone=True)) < now()))


    @contextmanager
    def topic_snapshot(self):
        """Headers plus a server-side vector cursor; never materialize the index."""
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
            with c.begin():
                revision = c.execute(select(datasets.c.revision).where(datasets.c.id == "shared")).scalar() or 0
                docs = [dict(row) for row in c.execute(select(documents.c.file_id, documents.c.filename,
                    documents.c.source_relpath, documents.c.media_type, documents.c.size_bytes, documents.c.updated_at).where(documents.c.active)).mappings()]
                latest = select(extractions.c.file_id, extractions.c.id).distinct(extractions.c.file_id).order_by(
                    extractions.c.file_id, extractions.c.created_at.desc(), extractions.c.id).subquery()
                title = artifacts.c.payload['response']['metadata']['document_title'].astext
                method = artifacts.c.payload['response']['metadata']['title_method'].astext
                metadata = artifacts.c.payload['response']['metadata']['document_metadata']
                titles = {}
                for row in c.execute(select(artifacts.c.file_id, title.label('document_title'), method.label('title_method'), metadata.label('document_metadata')).join(
                    latest, latest.c.file_id == artifacts.c.file_id).join(documents,documents.c.file_id == artifacts.c.file_id).where(artifacts.c.kind == 'synthesis',
                    artifacts.c.payload['input_extraction_id'].astext == func.coalesce(documents.c.metadata['primary_extraction_id'].astext,latest.c.id), or_(title.is_not(None), metadata.is_not(None))).order_by(
                    artifacts.c.payload['created_at'].astext.desc(), artifacts.c.id)).mappings():
                    titles.setdefault(row['file_id'], dict(row))
                from osii.domain.document_metadata import synthesis_labels
                corrections = {row['file_id']: synthesis_labels({'document_metadata':row['payload']['document_metadata']})
                    for row in c.execute(select(artifacts.c.file_id, artifacts.c.payload).where(artifacts.c.kind=='manual_metadata')).mappings()}
                for doc in docs:
                    doc.update(titles.get(doc['file_id'], {}))
                    doc.update(corrections.get(doc['file_id'], {}))
                def rows(allowed):
                    statement = select(chunks.c.file_id, chunks.c.embedding, chunks.c.embedding_model).where(
                        chunks.c.file_id.in_(allowed))
                    result = c.execution_options(stream_results=True, max_row_buffer=16).execute(statement)
                    try:
                        yield from result.mappings()
                    finally:
                        result.close()
                yield revision, docs, rows


    def document_text_lengths(self) -> dict[str, int]:
        with self.engine.connect() as c:
            return dict(c.execute(select(documents.c.source_relpath, func.length(documents.c.text)).where(documents.c.active)).all())


    def save_extraction_variant(self, file_id, sha256, response, *, job_owner=None):
        with self.transaction() as c:
            self.assert_job_owner(c, job_owner)
            doc = c.execute(select(documents).where(documents.c.file_id==file_id,documents.c.active).with_for_update()).mappings().first()
            if not doc:
                raise ValueError('A primary extraction is required before saving a variant')
            if not doc['metadata'].get('primary_extraction_id'):
                old = c.execute(select(extractions.c.id).where(extractions.c.file_id==file_id).order_by(extractions.c.created_at.desc(),extractions.c.id).limit(1)).scalar()
                c.execute(update(documents).where(documents.c.file_id==file_id).values(metadata={**doc['metadata'],'primary_extraction_id':old}))
            c.execute(insert(extractions).values(id=identifier(),file_id=file_id,sha256=sha256,response=response,created_at=now()))


    def catalog_documents(self) -> list[dict]:
        # Aggregate product presence once. Never load text, artifact payloads or
        # chunk vectors just to draw file cards.
        products = select(artifacts.c.file_id,
            func.bool_or(artifacts.c.kind == "synthesis").label("has_synthesis"),
            func.bool_or(artifacts.c.kind == "enrichment").label("has_enrichments")).group_by(artifacts.c.file_id).subquery()
        with self.engine.connect() as c:
            query = select(documents.c.file_id, documents.c.filename, documents.c.source_relpath,
                documents.c.media_type, documents.c.size_bytes, documents.c.updated_at,
                documents.c.metadata["source_modified_at"].astext.label("modified_at"),
                (func.length(func.trim(documents.c.text)) > 0).label("has_text"),
                func.coalesce(products.c.has_synthesis, False).label("has_synthesis"),
                func.coalesce(products.c.has_enrichments, False).label("has_enrichments"))
            return [dict(row) for row in c.execute(query.outerjoin(products, documents.c.file_id == products.c.file_id).where(documents.c.active)).mappings()]


    def cached_topic_map(self, key: str) -> dict | None:
        return self.setting("topic_map_cache:" + key, {}).get("result")

    def save_topic_map(self, key: str, result: dict) -> None:
        """Bounded derived geometry only; no user labels or document contents."""
        from sqlalchemy.dialects.postgresql import insert as upsert
        with self.transaction() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('osii:topic-map-cache'))"))
            stmt = upsert(settings).values(id="topic_map_cache:" + key, value={"created_at": now().isoformat(), "result": result})
            c.execute(stmt.on_conflict_do_update(index_elements=[settings.c.id], set_={"value": stmt.excluded.value}))
            old = select(settings.c.id).where(settings.c.id.like("topic_map_cache:%")).order_by(settings.c.value['created_at'].astext.desc(), settings.c.id).offset(16)
            c.execute(delete(settings).where(settings.c.id.in_(old)))


    @staticmethod
    def _metadata_id(file_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, 'osii:manual-metadata:'+file_id))

    def document_metadata(self, file_id: str) -> dict:
        with self.engine.connect() as c:
            doc=c.execute(select(documents.c.metadata).where(documents.c.file_id==file_id,documents.c.active)).scalar()
            if doc is None: raise LookupError('Unknown file_id')
            manual=c.execute(select(artifacts.c.payload).where(artifacts.c.id==self._metadata_id(file_id))).scalar()
            primary=doc.get('primary_extraction_id') or c.execute(select(extractions.c.id).where(extractions.c.file_id==file_id).order_by(extractions.c.created_at.desc(),extractions.c.id).limit(1)).scalar()
            generated=c.execute(select(artifacts.c.payload['response']['metadata']['document_metadata']).where(artifacts.c.file_id==file_id,
                artifacts.c.kind=='synthesis',artifacts.c.payload['input_extraction_id'].astext==primary).order_by(artifacts.c.payload['created_at'].astext.desc(),artifacts.c.id).limit(1)).scalar()
            return {'file_id':file_id,'revision':manual['revision'] if manual else None,
                'document_metadata':manual['document_metadata'] if manual else generated,'generated_metadata':generated}

    def save_document_metadata(self, file_id: str, values: dict, expected: str | None, actor: str) -> dict:
        from osii.processor_sdk import DocumentMetadata
        from sqlalchemy.dialects.postgresql import insert as upsert
        fields=('descriptive_title','title','author','date','agency','document_type')
        if not isinstance(values,dict) or set(values)-set(fields): raise ValueError('Provide document metadata fields only')
        record=DocumentMetadata.model_validate({'method':'human',**{field:{'value':values.get(field)} for field in fields}}).model_dump(mode='json')
        with self.transaction() as c:
            if c.execute(select(documents.c.file_id).where(documents.c.file_id==file_id,documents.c.active).with_for_update()).scalar() is None: raise LookupError('Unknown file_id')
            current=c.execute(select(artifacts.c.payload).where(artifacts.c.id==self._metadata_id(file_id)).with_for_update()).scalar()
            if (current['revision'] if current else None)!=expected: raise FileExistsError('Metadata changed; reload the latest revision and review your draft')
            if current: c.execute(insert(artifacts).values(id=identifier(),file_id=file_id,kind='manual_metadata_history',payload=current))
            payload={'revision':identifier(),'document_metadata':record,'created_at':now().isoformat(),'actor':actor}
            stmt=upsert(artifacts).values(id=self._metadata_id(file_id),file_id=file_id,kind='manual_metadata',payload=payload)
            c.execute(stmt.on_conflict_do_update(index_elements=[artifacts.c.id],set_={'payload':payload}))
        return self.document_metadata(file_id)
