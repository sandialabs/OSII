"""Hosted inventory evidence and versioned scope products, owned by Core."""

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from osii.persistence.postgres import metadata

inventory_sources = Table(
    "inventory_sources",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("relative_root", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("device", Text, nullable=False),
    Column("inode", Text, nullable=False),
    Column("generation", Integer, nullable=False, server_default="1"),
)
inventory_scans = Table(
    "inventory_scans",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source_id", BigInteger, ForeignKey("inventory_sources.id"), nullable=False),
    Column("job_id", String, ForeignKey("jobs.id"), nullable=False, unique=True),
    Column("created", Float, nullable=False),
    Column("updated", Float, nullable=False),
    Column("completed", Integer, nullable=False, server_default="0"),
    Column("failed", Integer, nullable=False, server_default="0"),
    Column("observed_entries", BigInteger, nullable=False, server_default="0"),
    Column("known_bytes", BigInteger, nullable=False, server_default="0"),
    Column("metadata_errors", Integer, nullable=False, server_default="0"),
    Column("error", Text),
)
inventory_directories = Table(
    "inventory_directories",
    metadata,
    Column("scan_id", BigInteger, ForeignKey("inventory_scans.id"), primary_key=True),
    Column("path", Text, primary_key=True),
    Column("status", String, nullable=False, server_default="pending"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Column("updated", Float),
)
inventory_entries = Table(
    "inventory_entries",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source_id", BigInteger, ForeignKey("inventory_sources.id"), nullable=False),
    Column("path", Text, nullable=False),
    Column("parent", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("kind", String, nullable=False),
    Column("suffix", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("mtime_ns", BigInteger, nullable=False),
    Column("ctime_ns", BigInteger, nullable=False),
    Column("device", Text),
    Column("inode", Text),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("status", String, nullable=False),
    Column("observed", Float, nullable=False),
    Column("seen_token", String, nullable=False),
    Column("metadata_state", String, nullable=False),
    Column("metadata_error", Text),
    Column("scan_run_id", BigInteger, ForeignKey("inventory_scans.id")),
    Column("file_id", String, ForeignKey("documents.file_id", ondelete="SET NULL")),
    UniqueConstraint("source_id", "path", name="inventory_entry_source_path"),
)
inventory_selections = Table(
    "inventory_selections",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("request", JSONB, nullable=False),
    Column("coverage", JSONB, nullable=False),
    Column("created", Float, nullable=False),
    Column("count", Integer, nullable=False, server_default="0"),
    Column("bytes", BigInteger, nullable=False, server_default="0"),
)
inventory_members = Table(
    "inventory_members",
    metadata,
    Column(
        "selection_id",
        BigInteger,
        ForeignKey("inventory_selections.id"),
        primary_key=True,
    ),
    Column(
        "entry_id", BigInteger, ForeignKey("inventory_entries.id"), primary_key=True
    ),
    Column("snapshot", JSONB, nullable=False),
)
inventory_events = Table(
    "inventory_events",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("scan_id", BigInteger, ForeignKey("inventory_scans.id"), nullable=False),
    Column("created", Float, nullable=False),
    Column("path", Text),
    Column("message", Text, nullable=False),
)
scope_products = Table(
    "scope_products",
    metadata,
    Column("id", String, primary_key=True),
    Column("scope_type", String, nullable=False),
    Column("scope_id", Text, nullable=False),
    Column("filename", String, nullable=False),
    Column("family", String, nullable=False),
    Column("method", String, nullable=False),
    Column("current_revision", String),
    Column("title", Text, nullable=False),
    Column("artifact_type", String, nullable=False),
    UniqueConstraint(
        "scope_type", "scope_id", "filename", name="scope_product_address"
    ),
)
scope_revisions = Table(
    "scope_revisions",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "product_id",
        String,
        ForeignKey("scope_products.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("parent", String),
    Column("origin", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("actor_id", String, ForeignKey("users.id", ondelete="SET NULL")),
    Column("data", JSONB, nullable=False),
    Column("provenance", JSONB, nullable=False),
)
