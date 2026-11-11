"""Explicit composition of Core storage ports; no implicit data migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import Mapping


@dataclass(frozen=True)
class BackendSettings:
    kind: str = "sidecar"
    # repr=False keeps credentials out of diagnostics and exception formatting.
    database_url: str = field(default="", repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None):
        env = os.environ if environment is None else environment
        kind = env.get("OSII_STORAGE_BACKEND", "sidecar").strip().lower()
        if kind not in {"sidecar", "postgres"}:
            raise ValueError("OSII_STORAGE_BACKEND must be sidecar or postgres")
        url = env.get("DATABASE_URL", "").strip() if kind == "postgres" else ""
        if kind == "postgres" and not url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("The postgres backend requires a PostgreSQL DATABASE_URL")
        return cls(kind, url)


def postgres_engine(settings: BackendSettings):
    if settings.kind != "postgres":
        raise ValueError("PostgreSQL was not selected")
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional osii[postgres] dependencies before selecting PostgreSQL"
        ) from exc
    # Hide SQL parameter values and do not expose the URL in startup errors.
    return create_engine(
        settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )


class LibraryBackend:
    """Application-owned ports. Configuration and file inventory stay separate."""

    def __init__(self, root: Path, settings: BackendSettings | None = None):
        self.settings = settings or BackendSettings.from_environment()
        self.root = Path(root).resolve()
        self.engine = None
        if self.settings.kind == "sidecar":
            from osii.domain.read.sidecar import SidecarLibraryReader
            from .sidecar_commits import SidecarProcessingCommitter
            from .sidecar_authoring import (
                SidecarProductAuthoring,
                SidecarCollectionStore,
            )
            from .sidecar_jobs import SidecarJobStore
            from osii.domain.artifacts.products import read_product

            self.reader = SidecarLibraryReader(self.root, product_reader=read_product)
            self.committer = SidecarProcessingCommitter(self.root)
            self.products = SidecarProductAuthoring(self.root)
            self.collections = SidecarCollectionStore(self.root)
            self.jobs = SidecarJobStore(self.root)
            from .text_authoring import SidecarTextAuthoring

            self.text = SidecarTextAuthoring(self.root)
        else:
            from osii.domain.read.postgres import PostgresLibraryReader
            from .postgres_commits import PostgresProcessingCommitter
            from .postgres_authoring import (
                PostgresProductAuthoring,
                PostgresCollectionStore,
            )
            from .postgres_jobs import PostgresJobStore
            from .postgres_schema import validate

            try:
                self.engine = postgres_engine(self.settings)
                validate(self.engine)
            except Exception:
                if self.engine is not None:
                    self.engine.dispose()
                raise RuntimeError(
                    "Cannot open the selected local PostgreSQL library. Check connectivity and run the explicit schema initialization; sidecars were not selected or changed."
                ) from None
            self.reader = PostgresLibraryReader(self.engine)
            self.committer = PostgresProcessingCommitter(self.engine)
            self.products = PostgresProductAuthoring(self.engine)
            self.collections = PostgresCollectionStore(self.engine)
            # A force-stopped Windows process cannot run a finally block. Short
            # local leases recover on restart without stealing live claims.
            self.jobs = PostgresJobStore(self.engine, lease_seconds=15)
            from .text_authoring import PostgresTextAuthoring

            self.text = PostgresTextAuthoring(self.engine)

    def close(self):
        if self.engine is not None:
            self.engine.dispose()
