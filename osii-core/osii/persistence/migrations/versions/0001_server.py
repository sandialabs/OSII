"""Initial shared library, accounts, sessions, and durable jobs.

This schema is frozen: later table changes require a new Alembic revision.
"""
from alembic import op
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        MetaData, String, Table, Text)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_server"
down_revision = None


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



def upgrade():
    metadata.create_all(op.get_bind())
    op.get_bind().execute(datasets.insert().values(id="shared", revision=0))


def downgrade():
    metadata.drop_all(op.get_bind())
