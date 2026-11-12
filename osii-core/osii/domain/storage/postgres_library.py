"""Standalone library application operations over the shared PostgreSQL ports.

Originals remain ordinary files. No hosted account model or sidecar fallback is
used here; the filesystem is only accessed by explicit source-file operations.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import uuid

from osii.domain.read.contracts import ReadScope
from .authoring import AuthoringConflict, ProductRef
from .retrieval import BoundedRetriever, RetrievalRequest


class PostgresLibrary:
    def __init__(self, backend):
        from osii.search.engine import RetrievalEngine

        self.backend = backend
        self.reader, self.engine = backend.reader, backend.engine
        self.ranker = RetrievalEngine()

    @staticmethod
    def sql(conn, statement, **values):
        from sqlalchemy import text

        return conn.execute(text(statement), values)

    def query(self, statement, **values):
        with self.engine.connect() as conn:
            return [dict(row) for row in self.sql(conn, statement, **values).mappings()]

    def setting(self, key, default=None):
        rows = self.query("SELECT value FROM settings WHERE id=:id", id=key)
        return rows[0]["value"] if rows else default

    def set_setting(self, key, value):
        with self.engine.begin() as conn:
            self.sql(
                conn,
                """INSERT INTO settings(id,value) VALUES (:id,CAST(:value AS jsonb))
                ON CONFLICT(id) DO UPDATE SET value=excluded.value""",
                id=key,
                value=json.dumps(value, ensure_ascii=False),
            )

    def inventory_links(self, inventory_connection, inventory_path):
        """Metadata-only status projection; the inventory remains authoritative."""
        import time

        rows = self.query(
            "SELECT file_id,metadata->'inventory_links' AS links FROM documents WHERE active"
        )
        allowed = {row["file_id"] for row in rows}
        result = [
            tuple(row)
            for row in inventory_connection.execute(
                "SELECT entry_id,revision,file_id,run_id,updated FROM main.sidecar_links"
            )
            if row["file_id"] in allowed
        ]
        for row in rows:
            for link in row["links"] or []:
                if link.get("inventory_database") == str(inventory_path):
                    result.append(
                        (
                            link["entry_id"],
                            link["revision"],
                            row["file_id"],
                            link["run_id"],
                            link.get("updated", time.time()),
                        )
                    )
        return result

    def scope(self, value):
        if isinstance(value, ReadScope):
            return value
        kind = value.get("scope_type", "root")
        key = {
            "object": "file_id",
            "folder": "folder_id",
            "collection": "collection_id",
        }.get(kind)
        identity = str(value.get(key, "")) if key else "root"
        if kind == "folder":
            folder = next(
                (row for row in self.folders() if row["folder_id"] == identity), None
            )
            if folder is None:
                raise KeyError("Folder not found")
            identity = folder["path"] or "."
        return ReadScope(kind, identity)

    def documents(self, scope=None):
        result, cursor = [], None
        while True:
            page = self.reader.list_documents(
                self.scope(scope or {}), limit=500, cursor=cursor
            )
            result.extend(page.items)
            cursor = page.next_cursor
            if not cursor:
                return result

    def folders(self):
        recorded = self.setting("sidecar_folders", [])
        by_path = {str(row.get("path", "")).strip("/"): dict(row) for row in recorded}
        for row in self.query(
            "SELECT DISTINCT source_relpath FROM documents WHERE active"
        ):
            path = PurePosixPath(row["source_relpath"]).parent
            while str(path) not in {"", "."}:
                name = path.as_posix()
                by_path.setdefault(
                    name,
                    {
                        "folder_id": "fld-"
                        + hashlib.sha256(name.encode()).hexdigest()[:16],
                        "path": name,
                    },
                )
                path = path.parent
        return sorted(by_path.values(), key=lambda row: (row["path"], row["folder_id"]))

    def describe(self, scope):
        read = self.scope(scope)
        kind = read.kind
        label = "Library"
        key = {
            "object": "file_id",
            "folder": "folder_id",
            "collection": "collection_id",
        }.get(kind)
        identity = scope.get(key, "root") if key else "root"
        if kind == "object":
            record = self.reader.get_document(read.identifier)
            if record is None:
                raise KeyError("Document not found")
            label = record.filename
        elif kind == "folder":
            label = read.identifier
        elif kind == "collection":
            record = self.backend.collections.get(read.identifier)
            if record is None:
                raise KeyError("Collection not found")
            label = record.name
        return {
            "scope_type": kind,
            "scope_id": identity,
            "label": label,
            **({key: identity} if key else {}),
            **({"path": read.identifier} if kind == "folder" else {}),
        }

    def collection_view(self, record):
        metadata = {
            **record.metadata,
            **self.setting("collection_metadata:" + record.collection_id, {}),
        }
        return {
            **metadata,
            "id": record.collection_id,
            "name": record.name,
            "description": record.description,
            "kind": metadata.get("kind", "manual"),
            "color": metadata.get("color"),
            "created_utc": metadata.get("created_utc"),
            "updated_utc": metadata.get("updated_utc"),
            "document_count": len(record.member_ids),
            "version": record.version,
        }

    def product_rows(self, scope, family=None):
        read = self.scope(scope)
        # Sidecar imports preserve logical folder IDs, while new shared commits
        # use source-relative paths. Accept both addresses without losing IDs.
        identifiers = [read.identifier]
        if read.kind == "folder" and isinstance(scope, dict):
            identifiers.append(scope.get("folder_id", ""))
        return self.query(
            """SELECT p.*,r.data,r.provenance,r.origin FROM scope_products p
            JOIN scope_revisions r ON r.id=p.current_revision
            WHERE p.scope_type=:kind AND (p.scope_id=:id OR p.scope_id=:legacy)
            AND (CAST(:family AS text) IS NULL OR p.family=:family) ORDER BY p.filename""",
            kind=read.kind,
            id=identifiers[0] or "root",
            legacy=identifiers[-1] or "root",
            family=family,
        )

    def product_view(self, scope, row):
        return {
            "name": row["filename"],
            "filename": row["filename"],
            "kind": "file",
            "artifact_type": row["artifact_type"],
            "method": row["method"],
            "title": row["title"],
            "scope_type": self.scope(scope).kind,
            "is_bundle": False,
            "can_edit": True,
            "current_revision": row["current_revision"],
            "data_path": f"products/{row['id']}",
            "metadata_path": f"products/{row['id']}/metadata",
            "relpath": f"products/{row['id']}",
            "family": row["family"],
        }

    def enrichments(self, scope):
        return [
            self.product_view(scope, row)
            for row in self.product_rows(scope, "enrichment")
        ]

    def syntheses(self, scope):
        return [
            {
                "name": row["method"],
                "text_path": f"products/{row['id']}",
                "relpath": f"products/{row['id']}",
                "toml_path": f"products/{row['id']}/metadata",
                "scope": self.scope(scope).kind,
            }
            for row in self.product_rows(scope, "synthesis")
        ]

    def synthesis(self, scope):
        rows = self.product_rows(scope, "synthesis")
        return (
            (rows[-1]["data"].get("markdown") or rows[-1]["data"].get("text"))
            if rows
            else None
        )

    def artifact_summary(self, scope):
        members = self.documents(scope)
        synthesis = self.synthesis(scope)
        enrichments = self.enrichments(scope)
        return {
            "scope": self.describe(scope),
            "artifact_summary": {
                "member_count": len(members),
                "has_synthesis": bool(synthesis),
                "synthesis_preview": synthesis[:500] if synthesis else None,
                "syntheses": self.syntheses(scope),
                "has_enrichments": bool(enrichments),
                "enrichments": enrichments,
            },
            "actions": {"can_synthesize": bool(members), "can_enrich": bool(members)},
        }

    def meta(self, file_id):
        document = self.reader.get_document(file_id)
        if document is None:
            raise KeyError("Document not found")
        return {
            **{
                k: v
                for k, v in document.metadata.items()
                if k
                not in {
                    "edited_text_history",
                    "edited_representation",
                    "inventory_links",
                }
            },
            "file": {
                **document.metadata.get("file", {}),
                "filename": document.filename,
                "source_relpath": document.source_relpath,
                "mime": document.media_type,
                "size_bytes": document.size_bytes,
            },
            "hash": {"sha256": document.sha256},
        }

    def manifest(self, file_id):
        canonical = self.reader.get_representation(file_id, "canonical")
        if canonical is None:
            raise KeyError("Document not found")
        return [
            {
                "id": row.segment_id,
                "kind": "text",
                "path": f"objects/{file_id}/text.txt",
                "span": {"char_start": row.char_start, "char_end": row.char_end},
                "source_origin": row.source_origin,
            }
            for row in canonical.segments
        ] + self.images(file_id)

    def images(self, file_id):
        result = []
        cursor = None
        while True:
            page = self.reader.list_artifacts(file_id, limit=500, cursor=cursor)
            for row in page.items:
                if row.media_type.startswith("image/"):
                    result.append(
                        {
                            "id": row.artifact_id,
                            "kind": "image",
                            "type": row.media_type,
                            "path": f"objects/{file_id}/artifacts/{row.artifact_id}",
                            "source_origin": row.metadata.get("source_origin", {}),
                        }
                    )
            cursor = page.next_cursor
            if not cursor:
                return result

    def processing(self, file_id):
        doc = self.reader.get_document(file_id)
        extractor = doc.metadata.get("extractor") or doc.metadata.get(
            "extraction_provenance", {}
        ).get("extractor", {})
        edited = doc.metadata.get("edited_representation") is not None
        syntheses = self.product_rows(
            {"scope_type": "object", "file_id": file_id}, "synthesis"
        )
        synthesizer = (
            syntheses[-1]["provenance"].get("processor", {}) if syntheses else {}
        )
        return {
            "extractor": {
                "name": extractor.get("name"),
                "display_name": extractor.get("display_name") or extractor.get("name"),
            },
            "synthesizer": {
                "name": synthesizer.get("name"),
                "display_name": synthesizer.get("display_name"),
            },
            "canonical_text_path": f"objects/{file_id}/text.txt",
            "editable_text_path": f"objects/{file_id}/edited_text.json"
            if edited
            else None,
            "has_editable_text": edited,
            "capabilities": {"supports_markdown_render": True},
        }

    def summaries(self, ids):
        # A file grid must not fetch every text revision or perform several
        # round-trips per card. Project just the fields this view displays.
        documents = {
            row["file_id"]: row
            for row in self.query(
                """SELECT file_id,filename,source_relpath,media_type,size_bytes,
            metadata->'file' AS file,metadata->'extractor' AS extractor,
            metadata ? 'edited_representation' AS edited,length(text)>0 AS has_text
            FROM documents WHERE active AND file_id IN(SELECT jsonb_array_elements_text(CAST(:ids AS jsonb)))""",
                ids=json.dumps(ids),
            )
        }
        products = {}
        for row in self.query(
            """SELECT p.scope_id,p.family,r.provenance->'processor' AS processor,
            left(COALESCE(r.data->>'markdown',r.data->>'text',''),500) AS preview
            FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision
            WHERE p.scope_type='object' AND p.scope_id IN(SELECT jsonb_array_elements_text(CAST(:ids AS jsonb))) ORDER BY p.filename""",
            ids=json.dumps(ids),
        ):
            products.setdefault(row["scope_id"], []).append(row)
        collections = self.backend.collections.list()
        collection_views = {
            c.collection_id: self.collection_view(c) for c in collections
        }
        rows = []
        for file_id in ids:
            doc = documents.get(file_id)
            if doc is None:
                continue
            saved = products.get(file_id, [])
            synthesis = next(
                (p for p in reversed(saved) if p["family"] == "synthesis"), None
            )
            extractor = doc["extractor"] or {}
            synthesizer = (synthesis or {}).get("processor") or {}
            rows.append(
                {
                    "file_id": file_id,
                    "filename": doc["filename"],
                    "source_relpath": doc["source_relpath"],
                    "source_file_relpath": doc["source_relpath"],
                    "mime": doc["media_type"],
                    "size_bytes": doc["size_bytes"],
                    "mtime_utc": (doc["file"] or {}).get("mtime_utc"),
                    "collections": [
                        collection_views[c.collection_id]
                        for c in collections
                        if file_id in c.member_ids
                    ],
                    "processing": {
                        "extractor": {
                            "name": extractor.get("name"),
                            "display_name": extractor.get("display_name")
                            or extractor.get("name"),
                        },
                        "synthesizer": {
                            "name": synthesizer.get("name"),
                            "display_name": synthesizer.get("display_name"),
                        },
                        "canonical_text_path": f"objects/{file_id}/text.txt",
                        "editable_text_path": f"objects/{file_id}/edited_text.json"
                        if doc["edited"]
                        else None,
                        "has_editable_text": doc["edited"],
                        "capabilities": {"supports_markdown_render": True},
                    },
                    "source_state": {
                        "status": "active",
                        "source_relpath": doc["source_relpath"],
                        "file_id": file_id,
                    },
                    "has_preferred_text": doc["has_text"] or doc["edited"],
                    "preferred_text_kind": "edited_text"
                    if doc["edited"]
                    else "canonical_extracted_text",
                    "has_synthesis": bool(synthesis),
                    "has_enrichments": any(p["family"] == "enrichment" for p in saved),
                    "synthesis_preview": synthesis["preview"] if synthesis else None,
                    "preview_available": True,
                }
            )
        return rows

    def overview(self, scope):
        from osii.domain.scopes.overview import _recorded_date, _date_histogram

        docs = self.documents(scope)
        counts = Counter(
            Path(row.filename).suffix.lower() or "(no extension)" for row in docs
        )
        size = sum(row.size_bytes or 0 for row in docs)
        indexed = sum(
            bool(row.metadata.get("embedding_identity"))
            and row.metadata["embedding_identity"].get("provider") != "local.hashing"
            and not row.metadata.get("stale", {}).get("embeddings")
            for row in docs
        )
        dates = {
            label: _date_histogram(
                [
                    date
                    for doc in docs
                    if (date := _recorded_date(doc.metadata.get("file", {}).get(key)))
                ],
                len(docs),
            )
            for label, key in (("created", "birthtime_utc"), ("modified", "mtime_utc"))
        }
        summaries = self.summaries([doc.file_id for doc in docs])
        return {
            "permissions": {"run": True},
            "scope": scope,
            "file_count": len(docs),
            "size_known_count": sum(row.size_bytes is not None for row in docs),
            "total_size_bytes": size,
            "average_size_bytes": size / len(docs) if docs else None,
            "missing_metadata_count": 0,
            "file_types": [
                {"label": key, "count": value} for key, value in sorted(counts.items())
            ],
            "dates": dates,
            "processing": {
                "text_count": len(docs),
                "synthesis_count": sum(row["has_synthesis"] for row in summaries),
                "enrichment_count": sum(row["has_enrichments"] for row in summaries),
                "indexed_count": indexed,
                "semantic_index": {
                    "status": "ready" if indexed else "missing",
                    "detail": "PostgreSQL chunk vectors"
                    if indexed
                    else "Build embeddings to enable semantic search",
                },
            },
            "warnings": [],
        }

    def history(self, payload):
        ref = self.product_ref(payload)
        history = self.backend.products.history(ref)
        revisions = [
            {
                "id": row.revision_id,
                "parent": row.parent_id,
                "origin": row.origin,
                "created_at": row.created_at,
                "data": row.data,
                "provenance": row.provenance,
                "grounding_needs_review": row.grounding_needs_review,
            }
            for row in history.revisions
        ]
        input_state = "unknown"
        frozen = (
            history.active.provenance.get("processing_input")
            if history.active
            else None
        )
        if frozen:
            from .commits import ScopeInputRevision, CommitConflict

            try:
                ScopeInputRevision.from_dict(frozen).verify(
                    self.reader, [d.file_id for d in self.documents(payload["scope"])]
                )
                input_state = "current"
            except CommitConflict:
                input_state = "stale"
        return {
            "current": history.active_revision,
            "data": history.active.data if history.active else None,
            "revisions": revisions,
            "library_id": self.library_id,
            "input_state": input_state,
        }

    def product_ref(self, payload):
        ref = ProductRef.from_scope(
            payload["scope"], payload["filename"], payload.get("family", "enrichment")
        )
        if ref.scope.kind == "folder":
            rows = self.product_rows(payload["scope"], ref.family)
            selected = next(
                (row for row in rows if row["filename"] == ref.filename), None
            )
            if selected:
                ref = ProductRef(
                    ReadScope("folder", selected["scope_id"]), ref.filename, ref.family
                )
        return ref

    def create_manual_product(self, ref, data):
        from .authoring import validate_product_edit

        data = validate_product_edit(data, data)
        identity = str(uuid.uuid4())
        revision = str(uuid.uuid4())
        with self.engine.begin() as conn:
            self.sql(
                conn,
                """INSERT INTO scope_products(id,scope_type,scope_id,filename,family,method,title,artifact_type)
                VALUES (:id,:kind,:scope,:name,:family,'manual',:title,:type)
                ON CONFLICT ON CONSTRAINT scope_product_address DO NOTHING""",
                id=identity,
                kind=ref.scope.kind,
                scope=ref.scope.identifier or "root",
                name=ref.filename,
                family=ref.family,
                title=data.get("title", ref.filename),
                type=data["artifact_type"],
            )
            product = (
                self.sql(
                    conn,
                    "SELECT * FROM scope_products WHERE scope_type=:kind AND scope_id=:scope AND filename=:name FOR UPDATE",
                    kind=ref.scope.kind,
                    scope=ref.scope.identifier or "root",
                    name=ref.filename,
                )
                .mappings()
                .one()
            )
            if product["current_revision"] is not None:
                raise AuthoringConflict(
                    "Product already exists; refresh before editing"
                )
            self.sql(
                conn,
                """INSERT INTO scope_revisions VALUES (:id,:product,NULL,'human',:created,NULL,CAST(:data AS jsonb),'{}')""",
                id=revision,
                product=product["id"],
                created=datetime.now(UTC).isoformat(),
                data=json.dumps(data),
            )
            self.sql(
                conn,
                "UPDATE scope_products SET current_revision=:revision WHERE id=:id",
                revision=revision,
                id=product["id"],
            )
        return revision

    @property
    def library_id(self):
        # A random persisted identity, not the credential-bearing database URL.
        value = self.setting("local_library_id")
        if not value:
            value = uuid.uuid4().hex
            with self.engine.begin() as conn:
                self.sql(
                    conn,
                    "INSERT INTO settings(id,value) VALUES ('local_library_id',CAST(:value AS jsonb)) ON CONFLICT(id) DO NOTHING",
                    value=json.dumps(value),
                )
            value = self.setting("local_library_id")
        return value

    def _deletion_state(self, conn, file_id, mode, source):
        if mode not in {"sidecar_only", "source_and_sidecar"}:
            raise ValueError("Choose a supported deletion mode")
        doc = (
            self.sql(
                conn, "SELECT * FROM documents WHERE file_id=:id AND active", id=file_id
            )
            .mappings()
            .first()
        )
        if doc is None:
            raise KeyError("Document not found")
        collections = [
            dict(row)
            for row in self.sql(
                conn,
                "SELECT id,name,members FROM collections WHERE members ? :id ORDER BY id",
                id=file_id,
            ).mappings()
        ]
        collection_ids = [row["id"] for row in collections]
        folder_rows = (
            self.sql(
                conn, "SELECT value FROM settings WHERE id='sidecar_folders'"
            ).scalar()
            or []
        )
        affected_folders = [
            row
            for row in folder_rows
            if not row["path"]
            or doc["source_relpath"].startswith(row["path"].rstrip("/") + "/")
        ]
        products = [
            dict(row)
            for row in self.sql(
                conn,
                """SELECT DISTINCT p.id,p.scope_type,p.scope_id,p.filename,p.current_revision
            FROM scope_products p LEFT JOIN scope_revisions r ON r.product_id=p.id WHERE
            (p.scope_type='object' AND p.scope_id=:id) OR p.scope_type='root' OR
            (p.scope_type='folder' AND (p.scope_id IN('', '.', 'root') OR left(:path,length(p.scope_id)+1)=p.scope_id||'/'
                OR p.scope_id IN(SELECT jsonb_array_elements_text(CAST(:folders AS jsonb))))) OR
            (p.scope_type='collection' AND p.scope_id IN(SELECT jsonb_array_elements_text(CAST(:collections AS jsonb)))) OR
            strpos(COALESCE(r.provenance::text,''),:id)>0 OR strpos(COALESCE(r.data::text,''),:id)>0 ORDER BY p.id""",
                id=file_id,
                path=doc["source_relpath"],
                collections=json.dumps(collection_ids),
                folders=json.dumps([row["folder_id"] for row in affected_folders]),
            ).mappings()
        ]
        source_path = str(source) if source else ""
        jobs = [
            dict(row)
            for row in self.sql(
                conn,
                """SELECT id,status FROM jobs WHERE strpos(payload::text,:id)>0
            OR (length(:path)>0 AND strpos(payload::text,:path)>0) ORDER BY id""",
                id=file_id,
                path=source_path,
            ).mappings()
        ]
        active = [
            {"id": row["id"], "run_id": row["id"], "status": row["status"]}
            for row in jobs
            if row["status"] in {"queued", "running", "pausing", "paused", "cancelling"}
        ]
        history = [
            row["id"]
            for row in jobs
            if row["status"]
            not in {"queued", "running", "pausing", "paused", "cancelling"}
        ]
        counts = (
            self.sql(
                conn,
                """SELECT (SELECT count(*) FROM extractions WHERE file_id=:id)+
            (SELECT count(*) FROM chunks WHERE file_id=:id)+(SELECT count(*) FROM artifacts WHERE file_id=:id)+1 AS count,
            octet_length(text)+pg_column_size(metadata) AS bytes FROM documents WHERE file_id=:id""",
                id=file_id,
            )
            .mappings()
            .one()
        )
        archive_prefixes = [
            f"objects/{file_id}/",
            "enrichments/",
            "syntheses/",
            ".history/",
        ]
        archive_prefixes += [f"collections/{identity}/" for identity in collection_ids]
        archive_prefixes += [
            f"folders/folder-{row['folder_id']}." for row in affected_folders
        ]
        for product in products:
            if product["scope_type"] == "object" and product["scope_id"] != file_id:
                archive_prefixes.extend(
                    [
                        f"objects/{product['scope_id']}/enrichments/",
                        f"objects/{product['scope_id']}/syntheses/",
                    ]
                )
        archives = [
            dict(row)
            for row in self.sql(
                conn,
                """SELECT import_id,path,sha256 FROM import_files WHERE
            left(path,5)='root.' OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(CAST(:prefixes AS jsonb)) p WHERE left(path,length(p))=p)
            OR position(convert_to(:id,'UTF8') in content)>0 ORDER BY import_id,path""",
                prefixes=json.dumps(archive_prefixes),
                id=file_id,
            ).mappings()
        ]
        stat = source.stat() if source else None
        snapshot = {
            "file_id": file_id,
            "mode": mode,
            "storage_backend": "postgres",
            "object_file_count": counts["count"],
            "object_bytes": counts["bytes"],
            "source_path": source_path or None,
            "source_size_bytes": stat.st_size if stat else None,
            "source_mtime_ns": stat.st_mtime_ns if stat else None,
            "source_identity": [stat.st_dev, stat.st_ino, stat.st_ctime_ns]
            if stat
            else None,
            "collections": [
                {"id": row["id"], "name": row["name"]} for row in collections
            ],
            "folders": affected_folders,
            "aggregate_paths": [
                f"{row['scope_type']}:{row['scope_id']}/{row['filename']}"
                for row in products
                if row["scope_type"] != "object"
            ],
            "active_jobs": active,
            "history_run_ids": history,
            "indexes_rebuild_required": bool(
                self.sql(
                    conn,
                    "SELECT 1 FROM chunks WHERE file_id=:id AND embedding IS NOT NULL LIMIT 1",
                    id=file_id,
                ).first()
            ),
            "source_will_be_deleted": mode == "source_and_sidecar"
            and source is not None,
            "source_will_remain": mode == "sidecar_only" and source is not None,
            "import_snapshot_files_removed": len(archives),
            "data_copy_note": "Only this PostgreSQL library is affected. Original sidecars, other libraries, database backups and WAL are not erased. Affected imported object and aggregate snapshots are also removed; other documents' source records and attachments remain.",
        }
        token_material = {
            **snapshot,
            "updated_at": doc["updated_at"].isoformat(),
            "products": products,
            "members": [r["members"] for r in collections],
            "archive": archives,
        }
        token = hashlib.sha256(
            json.dumps(token_material, sort_keys=True, default=str).encode()
        ).hexdigest()
        return (
            {**snapshot, "preview_token": token},
            [row["id"] for row in products],
            history,
            archives,
        )

    def deletion_preview(self, file_id, mode, source=None):
        with self.engine.begin() as conn:
            self.sql(conn, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return self._deletion_state(conn, file_id, mode, source)[0]

    def delete_document(self, file_id, mode, token, confirmation, source=None):
        if confirmation != file_id:
            raise ValueError("Confirmation must exactly match the document ID")
        retained = None
        try:
            with self.engine.begin() as conn:
                # Short deletion transaction only: no processor/model calls.
                self.sql(
                    conn,
                    "LOCK TABLE jobs,documents,extractions,chunks,artifacts,scope_products,scope_revisions,collections,settings,import_files IN SHARE ROW EXCLUSIVE MODE",
                )
                preview, products, jobs, archives = self._deletion_state(
                    conn, file_id, mode, source
                )
                if preview["preview_token"] != token:
                    raise AuthoringConflict(
                        "Deletion impact changed; review a fresh preview"
                    )
                if preview["active_jobs"]:
                    raise AuthoringConflict(
                        "Cancel the runs referencing this file before deleting it"
                    )
                if mode == "source_and_sidecar" and source is not None:
                    retained = source.with_name(".osii-delete-" + uuid.uuid4().hex)
                    if retained.exists():
                        raise FileExistsError("Temporary recovery path already exists")
                    source.rename(retained)
                self.sql(
                    conn,
                    "DELETE FROM scope_products WHERE id IN(SELECT jsonb_array_elements_text(CAST(:ids AS jsonb)))",
                    ids=json.dumps(products),
                )
                self.sql(
                    conn,
                    "UPDATE collections SET members=members-:id WHERE members ? :id",
                    id=file_id,
                )
                self.sql(
                    conn,
                    "DELETE FROM jobs WHERE id IN(SELECT jsonb_array_elements_text(CAST(:ids AS jsonb)))",
                    ids=json.dumps(jobs),
                )
                self.sql(conn, "DELETE FROM documents WHERE file_id=:id", id=file_id)
                self.sql(
                    conn,
                    "DELETE FROM settings WHERE strpos(id,:id)>0 OR strpos(value::text,:id)>0",
                    id=file_id,
                )
                self.sql(
                    conn,
                    "DELETE FROM import_files WHERE (import_id,path) IN(SELECT v->>'import_id',v->>'path' FROM jsonb_array_elements(CAST(:files AS jsonb)) v)",
                    files=json.dumps(archives),
                )
                self.sql(
                    conn,
                    "UPDATE settings SET value=value||jsonb_build_object('invalidated_by_deletion',true) WHERE id='sidecar_import' OR left(id,15)='sidecar_import:'",
                )
                self.sql(
                    conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'"
                )
        except Exception:
            if retained and retained.exists():
                if not source.exists():
                    retained.rename(source)
                else:
                    raise RuntimeError(
                        f"Database deletion failed. Original bytes remain at {retained}; restore them manually without overwriting {source}"
                    ) from None
            raise
        if retained is not None:
            try:
                retained.unlink()
            except OSError:
                if not source.exists():
                    retained.rename(source)
                raise RuntimeError(
                    f"OSII records were removed, but the original could not be deleted and remains at {source}"
                ) from None
        return {
            "ok": True,
            "file_id": file_id,
            "source_deleted": retained is not None,
            "storage_backend": "postgres",
        }

    def chunks(self, scope):
        ids = [doc.file_id for doc in self.documents(scope)]
        with self.engine.begin() as conn:
            self.sql(conn, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            revision = self.sql(
                conn, "SELECT revision FROM datasets WHERE id='shared'"
            ).scalar()
            rows = [
                dict(row)
                for row in self.sql(
                    conn,
                    """SELECT c.*,d.filename,d.source_relpath,
                (d.metadata-'edited_text_history'-'edited_representation') || jsonb_build_object('has_edited_text',d.metadata ? 'edited_representation') AS metadata FROM chunks c
                JOIN documents d ON d.file_id=c.file_id WHERE d.active
                AND c.file_id IN (SELECT jsonb_array_elements_text(CAST(:ids AS jsonb))) ORDER BY c.file_id,c.char_start,c.chunk_id""",
                    ids=json.dumps(ids),
                ).mappings()
            ]
        return revision, rows

    def retrieve(self, request):
        return BoundedRetriever(self._search).retrieve(request)

    def _search(self, request: RetrievalRequest):
        revision, rows = self.chunks(request.scope)
        vector, model, warning = None, "", None
        identities = {
            json.dumps(row["metadata"].get("embedding_identity"), sort_keys=True)
            for row in rows
            if row.get("embedding")
        }
        if request.mode != "lexical" and len(identities) == 1:
            identity = json.loads(next(iter(identities)))
            if identity and identity.get("provider") != "local.hashing":
                from osii.processors.remote import (
                    resolve_remote_processor,
                    _commit_descriptor,
                )
                from osii.processor_sdk import (
                    ProcessorClient,
                    EmbeddingInput,
                    EmbeddingRequest,
                )
                from osii.domain.processing.postgres_workflow import (
                    embedding_binding,
                    model_request,
                )

                try:
                    producers = {
                        row["metadata"]
                        .get("embedding_provenance", {})
                        .get("processor", {})
                        .get("name")
                        for row in rows
                        if row.get("embedding")
                    }
                    producers.discard(None)
                    if len(producers) > 1:
                        raise ValueError("Incompatible processor identities")
                    descriptor = resolve_remote_processor(
                        next(iter(producers)) if producers else identity["provider"],
                        "embedder",
                    )
                    expected = _commit_descriptor(descriptor)
                    binding = embedding_binding(
                        self.backend.root, expected, descriptor["base_url"]
                    )
                    if identity.get("connection_fingerprint") != binding:
                        raise ValueError(
                            "Embedding connection changed; rebuild the index"
                        )
                    with model_request(
                        self.backend.root, expected, uuid.uuid4().hex
                    ) as context:
                        query_request = EmbeddingRequest(
                            request_id=uuid.uuid4().hex,
                            inputs=[EmbeddingInput(id="query", text=request.query)],
                            config={"model": identity["model"]},
                            model_context=context,
                        )
                        response = ProcessorClient(descriptor["base_url"]).embed(
                            query_request
                        )
                    response = response.model_copy(
                        update={
                            "metadata": {
                                **response.metadata,
                                "connection_fingerprint": binding,
                            }
                        }
                    )
                    from .commits import (
                        embedding_identity,
                        InputRevision,
                        ProcessingCommit,
                        text_digest,
                    )

                    ProcessingCommit(
                        query_request.request_id,
                        "query",
                        query_request,
                        response,
                        expected,
                        input_revision=InputRevision(
                            "query", "query", text_digest(request.query)
                        ),
                    ).validate()

                    actual = embedding_identity(response)
                    fields = (
                        "provider",
                        "model",
                        "dimensions",
                        "normalized",
                        "model_digest",
                        "endpoint_type",
                        "connection_fingerprint",
                    )
                    if any(actual.get(key) != identity.get(key) for key in fields):
                        raise ValueError(
                            "Query embedding vector space changed; rebuild this index"
                        )
                    vector, model = response.vectors[0].vector, response.model
                except Exception:
                    warning = (
                        "Semantic embedding unavailable or incompatible; using BM25."
                    )
        if request.mode == "semantic" and vector is None:
            raise ValueError(
                "Semantic search needs an available embedder matching the indexed provider and model"
            )
        result, channels = self.ranker.search(
            rows,
            request.query,
            revision=revision,
            mode=request.mode,
            top_k=request.top_k,
            query_vector=vector,
            embedding_model=model,
        )
        if request.group_by == "file":
            from osii.domain.services.search import _group_results_by_file

            result = _group_results_by_file(result, top_k=request.top_k)
        for row in result:
            row["source_text_representation"] = (
                "edited" if row["metadata"].get("has_edited_text") else "canonical"
            )
            row["source_extraction_id"] = row["metadata"].get("primary_extraction_id")
            row.pop("metadata", None)
        mode = (
            "hybrid"
            if "semantic" in channels and len(channels) > 1
            else "semantic"
            if channels == ["semantic"]
            else "lexical"
        )
        return {
            "query": request.query,
            "mode": request.mode,
            "retrieval_mode_used": mode,
            "channels_used": channels,
            "corpus_revision": revision,
            "warning": warning,
            "results": result,
        }
