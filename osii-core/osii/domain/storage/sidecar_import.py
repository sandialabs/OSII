"""Explicit one-way import. Never opens source files for writing.

The normalized library is accompanied by an exact canonical-source snapshot so
legacy descriptors and attachments are not discarded by normalization. Caches,
operational queues, credentials, configuration and original files are excluded.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tomllib
import uuid

from osii.domain.read.sidecar import SidecarLibraryReader


@dataclass(frozen=True)
class ImportFile:
    path: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class ImportPlan:
    root: Path
    files: tuple[ImportFile, ...]
    excluded: tuple[str, ...]

    @property
    def fingerprint(self):
        return hashlib.sha256(
            json.dumps([(r.path, r.sha256) for r in self.files]).encode()
        ).hexdigest()

    def summary(self):
        return {
            "source": str(self.root),
            "canonical_files": len(self.files),
            "bytes": sum(len(row.content) for row in self.files),
            "fingerprint": self.fingerprint,
            "excluded": list(self.excluded),
            "changes_source": False,
            "destination_must_be_empty": True,
        }


def plan_import(root: Path) -> ImportPlan:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Choose an existing OSII sidecar directory")
    files, excluded = [], []
    # The allowlist is intentionally narrower than a library-directory copy.
    directories = {
        "objects",
        "folders",
        "collections",
        "enrichments",
        "syntheses",
        ".history",
    }
    root_names = {
        "root.toml",
        "root.overview.toml",
        "root.synth.toml",
        "root.synth.txt",
        "expert-context.md",
        "keyword_sets.toml",
    }
    candidates = []
    for child in sorted(root.iterdir()):
        if child.name not in directories | root_names:
            excluded.append(child.name + ("/" if child.is_dir() else ""))
            continue
        candidates.append(child)
        if child.is_dir() and not child.is_symlink():
            candidates.extend(child.rglob("*"))
    for path in sorted(candidates):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"Import refuses symlinks: {relative.as_posix()}")
        if not path.is_file():
            continue
        parts = relative.parts
        allowed = parts[0] in directories or len(parts) == 1 and path.name in root_names
        # Locks, secrets and transient writes have no place in an export.
        allowed = allowed and not any(
            p in {".env", "secrets.env", "__pycache__"} for p in parts
        )
        allowed = allowed and not path.name.endswith((".lock", ".tmp", ".pyc"))
        if not allowed:
            excluded.append(relative.as_posix())
            continue
        content = path.read_bytes()
        files.append(
            ImportFile(
                relative.as_posix(), hashlib.sha256(content).hexdigest(), content
            )
        )
    # Collections from older stores can be imported without opening SQLite in
    # writable mode or modifying the source into the newer portable layout.
    legacy = root / ".collections" / "collections.sqlite"
    if legacy.is_file():
        raise ValueError(
            "This library still uses legacy .collections SQLite membership. Export its collections to canonical collection.toml/members.jsonl before importing; no data was changed"
        )
    if not any(
        row.path.endswith("/meta.toml") and row.path.startswith("objects/")
        for row in files
    ):
        raise ValueError("No document descriptors were found in this sidecar directory")
    return ImportPlan(root, tuple(files), tuple(excluded))


def _json(value):
    return json.dumps(
        value, ensure_ascii=False, default=lambda x: x.isoformat(), allow_nan=False
    )


def _sql(conn, query, **values):
    from sqlalchemy import text

    return conn.execute(text(query), values)


def apply_import(engine, plan: ImportPlan, *, merge: bool = False) -> dict:
    """All-or-nothing import into an initialized, empty *local* schema.

    Caller explicitly chooses the destination. Running apps must be stopped;
    a PostgreSQL transaction and destination locks reject conflicting writes.
    A changed source is rejected before the transaction can commit.
    """
    from osii.domain.storage.postgres_schema import validate
    from osii.domain.artifacts.products import read_product
    from osii.domain.storage.sidecar_authoring import SidecarCollectionStore

    validate(engine)
    reader = SidecarLibraryReader(plan.root, product_reader=read_product)
    files = {row.path: row for row in plan.files}
    document_ids = sorted(
        {
            Path(row.path).parts[1]
            for row in plan.files
            if row.path.startswith("objects/")
            and Path(row.path).name == "meta.toml"
            and len(Path(row.path).parts) == 3
        }
    )

    def parsed(path, default=None):
        row = files.get(path)
        if row is None:
            return default
        if path.endswith(".toml"):
            return tomllib.loads(row.content.decode("utf-8"))
        return json.loads(row.content)

    def insert_setting(conn, key, value):
        _sql(
            conn,
            "INSERT INTO settings(id,value) VALUES (:id,CAST(:value AS jsonb)) ON CONFLICT(id) DO NOTHING",
            id=key,
            value=_json(value),
        )

    counts = {
        "documents": 0,
        "extractions": 0,
        "artifacts": 0,
        "collections": 0,
        "products": 0,
        "revisions": 0,
    }
    with engine.begin() as conn:
        _sql(conn, "SELECT pg_advisory_xact_lock(914035)")
        if merge:
            previous = _sql(
                conn,
                "SELECT value FROM settings WHERE id=:id",
                id="sidecar_import:" + plan.fingerprint,
            ).scalar()
            if previous and not previous.get("invalidated_by_deletion"):
                return {**previous, "imported": True, "replayed": True}
        for table in (
            "documents",
            "extractions",
            "chunks",
            "artifacts",
            "collections",
            "jobs",
            "scope_products",
            "scope_revisions",
            "settings",
            "import_files",
        ):
            _sql(conn, f"LOCK TABLE {table} IN EXCLUSIVE MODE")
            if (
                not merge
                and _sql(conn, f"SELECT EXISTS(SELECT 1 FROM {table})").scalar()
            ):
                raise ValueError(
                    "Import requires an empty destination library; nothing was changed"
                )
        for file_id in document_ids:
            document = reader.get_document(file_id)
            canonical = reader.get_representation(file_id, "canonical")
            if canonical is None:
                raise ValueError(
                    f"Document {file_id} has no canonical extracted text; import was rolled back"
                )
            metadata = dict(document.metadata)
            existing = (
                _sql(
                    conn,
                    "SELECT * FROM documents WHERE file_id=:id FOR UPDATE",
                    id=file_id,
                )
                .mappings()
                .first()
            )
            index = parsed(f"objects/{file_id}/extractions/index.json", {})
            metadata.update(
                primary_extraction_id=index.get("primary_id") or "canonical",
                segments=[
                    {
                        "id": seg.segment_id,
                        "char_start": seg.char_start,
                        "char_end": seg.char_end,
                        "source_origin": seg.source_origin,
                    }
                    for seg in canonical.segments
                ],
                extraction_provenance=canonical.provenance,
                sidecar_source={
                    "file_id": file_id,
                    "import_fingerprint": plan.fingerprint,
                },
            )
            edited = parsed(f"objects/{file_id}/edited_text.json")
            if edited is not None:
                preferred = reader.get_representation(file_id)
                metadata["edited_representation"] = {
                    "text": preferred.text,
                    "segments": edited.get("segments", []),
                    "revision": hashlib.sha256(
                        files[f"objects/{file_id}/edited_text.json"].content
                    ).hexdigest(),
                }
            history = parsed(f"objects/{file_id}/edited_text.history.json")
            if history is not None:
                metadata["edited_text_history"] = history
            if existing is not None:
                old_preferred = (
                    existing["metadata"]
                    .get("edited_representation", {})
                    .get("text", existing["text"])
                )
                new_preferred = metadata.get("edited_representation", {}).get(
                    "text", canonical.text
                )
                if (
                    existing["sha256"] != (document.sha256 or "")
                    or existing["text"] != canonical.text
                    or old_preferred != new_preferred
                ):
                    raise ValueError(
                        "Document text conflicts with the destination; the entire import was rolled back. Import into a fresh library to compare representations safely"
                    )
            # Index files are intentionally not transferred. Rebuild lexical
            # chunks from the saved preferred text, never from originals.
            for key in (
                "embedding_identity",
                "embedding_model",
                "embedding_provenance",
                "embedding_commit_id",
            ):
                metadata.pop(key, None)
            metadata["stale"] = {
                **metadata.get("stale", {}),
                "embeddings": True,
                "search_chunks": False,
            }
            _sql(
                conn,
                """INSERT INTO documents(file_id,source_relpath,sha256,filename,media_type,size_bytes,text,metadata)
                VALUES (:id,:path,:sha,:name,:mime,:size,:text,CAST(:metadata AS jsonb)) ON CONFLICT(file_id) DO NOTHING""",
                id=file_id,
                path=document.source_relpath,
                sha=document.sha256 or "",
                name=document.filename,
                mime=document.media_type or "application/octet-stream",
                size=document.size_bytes or 0,
                text=canonical.text,
                metadata=_json(metadata),
            )
            if existing is None:
                from osii.indexing.chunking import chunk_saved_text

                preferred = metadata.get("edited_representation", {}).get(
                    "text", canonical.text
                )
                grounding = (
                    ()
                    if metadata.get("edited_representation")
                    else metadata["segments"]
                )
                for chunk in chunk_saved_text(file_id, preferred, grounding):
                    _sql(
                        conn,
                        "INSERT INTO chunks(chunk_id,file_id,text,char_start,char_end,source_origin) VALUES(:chunk_id,:file_id,:text,:char_start,:char_end,CAST(:source_origin AS jsonb))",
                        **{**chunk, "source_origin": _json(chunk["source_origin"])},
                    )
            counts["documents"] += int(existing is None)
            governance = parsed(f"objects/{file_id}/governance.toml")
            if governance is not None:
                value = governance.get("governance", {})
                old = _sql(
                    conn,
                    "SELECT value FROM settings WHERE id=:id",
                    id="governance:" + file_id,
                ).scalar()
                if old:
                    from osii.domain.governance import _clean_values

                    value = {
                        **old,
                        "sensitivity_labels": _clean_values(
                            [
                                *old.get("sensitivity_labels", []),
                                *value.get("sensitivity_labels", []),
                            ]
                        ),
                        "tags": _clean_values(
                            [*old.get("tags", []), *value.get("tags", [])]
                        ),
                        "handling_notes": "\n\n".join(
                            dict.fromkeys(
                                x
                                for x in (
                                    old.get("handling_notes"),
                                    value.get("handling_notes"),
                                )
                                if x
                            )
                        ),
                    }
                    _sql(
                        conn,
                        "UPDATE settings SET value=CAST(:value AS jsonb) WHERE id=:id",
                        id="governance:" + file_id,
                        value=_json(value),
                    )
                else:
                    insert_setting(conn, "governance:" + file_id, value)
            expert = files.get(f"objects/{file_id}/expert-context.md")
            if expert is not None:
                insert_setting(
                    conn,
                    "expert-context:object:" + file_id,
                    expert.content.decode("utf-8"),
                )
            keywords = parsed(f"objects/{file_id}/enrichments/keywords--manual.json")
            if keywords is not None:
                insert_setting(
                    conn, "manual_keywords:" + file_id, keywords.get("keywords", [])
                )
            variants = [("canonical", canonical)]
            for variant in index.get("variants", []):
                if variant["id"] != "canonical":
                    record = reader.get_representation(file_id, variant["id"])
                    if record is None:
                        raise ValueError(
                            f"Missing extraction {variant['id']} for {file_id}"
                        )
                    variants.append((variant["id"], record))
            for variant_id, record in variants:
                # Exact text and offsets are preserved, not reconstructed with
                # an assumed separator by the destination reader.
                response = {
                    "processor": record.provenance.get("extractor", {}),
                    "segments": [
                        {
                            "id": seg.segment_id,
                            "text": seg.text,
                            "source_origin": seg.source_origin,
                        }
                        for seg in record.segments
                    ],
                    "metadata": {
                        "imported": True,
                        "source_representation_id": variant_id,
                    },
                    "osii_representation": {
                        "text": record.text,
                        "segments": [
                            {
                                "id": seg.segment_id,
                                "char_start": seg.char_start,
                                "char_end": seg.char_end,
                                "source_origin": seg.source_origin,
                            }
                            for seg in record.segments
                        ],
                        "provenance": record.provenance,
                    },
                }
                identity = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"osii-import:{file_id}:{variant_id}"
                    )
                )
                response["metadata"]["source_representation_id"] = variant_id
                _sql(
                    conn,
                    """INSERT INTO extractions(id,file_id,sha256,response) VALUES (:id,:file,:sha,CAST(:response AS jsonb)) ON CONFLICT(id) DO NOTHING""",
                    id=identity,
                    file=file_id,
                    sha=document.sha256 or "",
                    response=_json(response),
                )
                if variant_id == metadata["primary_extraction_id"]:
                    metadata["primary_extraction_id"] = identity
                counts["extractions"] += 1
            if existing is None:
                _sql(
                    conn,
                    "UPDATE documents SET metadata=CAST(:metadata AS jsonb) WHERE file_id=:id",
                    id=file_id,
                    metadata=_json(metadata),
                )
            manifest_file = files.get(f"objects/{file_id}/manifest.jsonl")
            manifest_records = (
                {
                    row.get("path"): row
                    for row in (
                        json.loads(line)
                        for line in manifest_file.content.splitlines()
                        if line.strip()
                    )
                }
                if manifest_file
                else {}
            )
            cursor = None
            while True:
                page = reader.list_artifacts(file_id, cursor=cursor, limit=500)
                for artifact in page.items:
                    content = reader.get_artifact(
                        file_id, artifact.artifact_id, max_bytes=None
                    )
                    identity = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"osii-import-artifact:{file_id}:{artifact.artifact_id}",
                        )
                    )
                    payload = {
                        "id": artifact.artifact_id,
                        "kind": artifact.kind,
                        "media_type": artifact.media_type,
                        "title": artifact.title,
                        "data_base64": base64.b64encode(content.data).decode(),
                        "metadata": artifact.metadata,
                        "source_origin": manifest_records.get(
                            artifact.artifact_id, {}
                        ).get("source_origin", {}),
                    }
                    old = _sql(
                        conn, "SELECT payload FROM artifacts WHERE id=:id", id=identity
                    ).scalar()
                    if old is not None and old != payload:
                        raise ValueError(
                            "Artifact address conflicts with an existing artifact; the entire import was rolled back"
                        )
                    _sql(
                        conn,
                        "INSERT INTO artifacts VALUES (:id,:file,:kind,CAST(:payload AS jsonb)) ON CONFLICT(id) DO NOTHING",
                        id=identity,
                        file=file_id,
                        kind=artifact.kind,
                        payload=_json(payload),
                    )
                    counts["artifacts"] += 1
                cursor = page.next_cursor
                if not cursor:
                    break
        for collection in SidecarCollectionStore(plan.root).list():
            if not set(collection.member_ids).issubset(document_ids):
                raise ValueError(
                    f"Collection {collection.collection_id} references unavailable documents"
                )
            previous = (
                _sql(
                    conn,
                    "SELECT name,members FROM collections WHERE id=:id FOR UPDATE",
                    id=collection.collection_id,
                )
                .mappings()
                .first()
            )
            if previous and previous["name"] != collection.name:
                raise ValueError(
                    "Collection identity conflicts with the destination; the entire import was rolled back"
                )
            _sql(
                conn,
                """INSERT INTO collections(id,name,description,members,visibility)
                VALUES (:id,:name,:description,CAST(:members AS jsonb),'shared') ON CONFLICT(id) DO NOTHING""",
                id=collection.collection_id,
                name=collection.name,
                description=collection.description or "",
                members=_json(collection.member_ids),
            )
            if previous:
                _sql(
                    conn,
                    "UPDATE collections SET members=CAST(:members AS jsonb) WHERE id=:id",
                    id=collection.collection_id,
                    members=_json(
                        sorted(set(previous["members"]) | set(collection.member_ids))
                    ),
                )
            insert_setting(
                conn,
                "collection_metadata:" + collection.collection_id,
                collection.metadata,
            )
            counts["collections"] += 1
        folder_rows = []
        for row in plan.files:
            parts = Path(row.path).parts
            if len(parts) == 2 and parts[0] == "folders" and row.path.endswith(".toml"):
                value = parsed(row.path)
                node = value.get("node", {})
                if node.get("folder_id"):
                    folder_rows.append(
                        {
                            "folder_id": node["folder_id"],
                            "path": node.get("path_hint", ""),
                        }
                    )
            if row.path == "expert-context.md":
                insert_setting(
                    conn, "expert-context:root:root", row.content.decode("utf-8")
                )
            if row.path == "keyword_sets.toml":
                insert_setting(
                    conn,
                    "keyword_sets",
                    parsed(row.path).get("keyword_sets", {}).get("sets", []),
                )
            if row.path in {"root.toml", "root.overview.toml"}:
                insert_setting(conn, "sidecar:" + row.path, parsed(row.path))
        insert_setting(conn, "sidecar_folders", folder_rows)
        # Normalize all scope product histories. Legacy material is preserved in
        # import_files even if it is not a currently active editable product.
        addresses = set()
        for row in plan.files:
            parts = Path(row.path).parts
            if ".history" in parts and parts[-1] == "manifest.json":
                manifest = parsed(row.path)
                name = manifest.get("filename", "")
                base = Path(row.path).parents[2]
                if Path(name).name != name:
                    raise ValueError("Invalid product history filename")
                target = (base / name).as_posix()
                if target == "root.synth.txt":
                    addresses.add(("root", "root", "synthesis", target))
                elif (
                    len(base.parts) == 2
                    and base.parts[0] == "objects"
                    and name == "synth.txt"
                ):
                    addresses.add(("object", base.parts[1], "synthesis", target))
                elif (
                    base.as_posix() == "folders"
                    and name.startswith("folder-")
                    and name.endswith(".synth.txt")
                ):
                    addresses.add(("folder", name[7:-10], "synthesis", target))
            if (
                parts[0] == "objects"
                and len(parts) >= 4
                and parts[2] in {"enrichments", "syntheses"}
            ):
                scope, sid, directory, rest = "object", parts[1], parts[2], parts[3:]
            elif (
                parts[0] == "collections"
                and len(parts) >= 4
                and parts[2] in {"enrichments", "syntheses"}
            ):
                scope, sid, directory, rest = (
                    "collection",
                    parts[1],
                    parts[2],
                    parts[3:],
                )
            elif (
                parts[0] == "folders"
                and len(parts) >= 3
                and parts[1].endswith((".enrichments", ".syntheses"))
            ):
                stem, directory = parts[1].rsplit(".", 1)
                scope, sid, rest = "folder", stem.removeprefix("folder-"), parts[2:]
            elif parts[0] in {"enrichments", "syntheses"}:
                scope, sid, directory, rest = "root", "root", parts[0], parts[1:]
            else:
                # Compatibility syntheses predate per-method directories.
                if row.path == "root.synth.txt":
                    addresses.add(("root", "root", "synthesis", row.path))
                elif (
                    len(parts) == 3
                    and parts[0] == "objects"
                    and parts[2] == "synth.txt"
                ):
                    addresses.add(("object", parts[1], "synthesis", row.path))
                elif (
                    len(parts) == 2
                    and parts[0] == "folders"
                    and parts[1].startswith("folder-")
                    and parts[1].endswith(".synth.txt")
                ):
                    addresses.add(("folder", parts[1][7:-10], "synthesis", row.path))
                continue
            family = "enrichment" if directory == "enrichments" else "synthesis"
            if (
                len(rest) == 1
                and Path(rest[0]).suffix in {".json", ".md", ".txt"}
                and not rest[0].endswith(".meta.json")
            ):
                addresses.add((scope, sid, family, row.path))
            elif (
                len(rest) == 3 and rest[0] == ".history" and rest[-1] == "manifest.json"
            ):
                manifest = parsed(row.path)
                name = manifest.get("filename")
                if not name or Path(name).name != name:
                    raise ValueError("Invalid product history filename")
                path = Path(row.path).parents[2] / name
                addresses.add((scope, sid, family, path.as_posix()))
        for scope, sid, family, path in sorted(addresses):
            history = read_product(plan.root / path)
            if not history["revisions"]:
                continue
            filename = (
                "current"
                if family == "synthesis"
                and (
                    path == "root.synth.txt"
                    or path.endswith("/synth.txt")
                    or "/" in path
                    and Path(path).parent.name == "folders"
                    and path.endswith(".synth.txt")
                )
                else Path(path).name
            )
            product_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"osii-import-product:{scope}:{sid}:{family}:{filename}",
                )
            )
            data = history.get("data") or history["revisions"][-1]["data"]
            prior = (
                _sql(
                    conn,
                    "SELECT id,current_revision FROM scope_products WHERE scope_type=:scope AND scope_id=:sid AND filename=:name FOR UPDATE",
                    scope=scope,
                    sid=sid,
                    name=filename,
                )
                .mappings()
                .first()
            )
            if prior:
                product_id = prior["id"]
            revision_ids = {
                revision["id"]: str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        product_id
                        + ":"
                        + (revision.get("provenance") or {}).get(
                            "sidecar_revision_id", revision["id"]
                        ),
                    )
                )
                for revision in history["revisions"]
            }
            _sql(
                conn,
                """INSERT INTO scope_products VALUES (:id,:scope,:sid,:name,:family,'imported',:current,:title,:kind) ON CONFLICT ON CONSTRAINT scope_product_address DO NOTHING""",
                id=product_id,
                scope=scope,
                sid=sid,
                name=filename,
                family=family,
                current=revision_ids.get(history["current"]),
                title=data.get("title", Path(path).name),
                kind=data.get("artifact_type", "text"),
            )
            for revision in history["revisions"]:
                saved_revision = _sql(
                    conn,
                    "SELECT data FROM scope_revisions WHERE id=:id",
                    id=revision_ids[revision["id"]],
                ).scalar()
                if saved_revision is not None and saved_revision != revision["data"]:
                    raise ValueError(
                        "A product revision conflicts with the destination; import was rolled back"
                    )
                _sql(
                    conn,
                    """INSERT INTO scope_revisions VALUES (:id,:product,:parent,:origin,:created,:actor,
                    CAST(:data AS jsonb),CAST(:provenance AS jsonb)) ON CONFLICT(id) DO NOTHING""",
                    id=revision_ids[revision["id"]],
                    product=product_id,
                    parent=revision_ids.get(revision.get("parent")),
                    origin=revision["origin"],
                    created=revision.get("created_at") or datetime.now(UTC).isoformat(),
                    actor=revision.get("actor_id"),
                    data=_json(revision["data"]),
                    provenance=_json(
                        {
                            **(revision.get("provenance") or {}),
                            "sidecar_revision_id": revision["id"],
                        }
                    ),
                )
                counts["revisions"] += 1
            counts["products"] += 1
        # Normalized products are the editable read path. Keep exact legacy
        # bytes in the archive, not a second stale artifact card.
        _sql(
            conn,
            """DELETE FROM artifacts a USING scope_products p WHERE p.scope_type='object'
            AND p.scope_id=a.file_id AND a.payload->>'id' IN('enrichments/'||p.filename,'syntheses/'||p.filename)""",
        )
        for row in plan.files:
            _sql(
                conn,
                "INSERT INTO import_files VALUES (:import_id,:path,:sha,:content) ON CONFLICT(import_id,path) DO NOTHING",
                import_id=plan.fingerprint,
                path=row.path,
                sha=row.sha256,
                content=row.content,
            )
        # Verify the complete source snapshot again, including additions, before
        # publication. No queues are resumed and no indexes are silently copied.
        if plan_import(plan.root).fingerprint != plan.fingerprint:
            raise ValueError(
                "Source sidecars changed during import; destination transaction was rolled back"
            )
        receipt = {
            **plan.summary(),
            **counts,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        insert_setting(conn, "sidecar_import", receipt)
        insert_setting(conn, "sidecar_import:" + plan.fingerprint, receipt)
        _sql(
            conn,
            "UPDATE settings SET value=CAST(:value AS jsonb) WHERE id=:id",
            id="sidecar_import:" + plan.fingerprint,
            value=_json(receipt),
        )
        _sql(conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'")
    return {
        **plan.summary(),
        **counts,
        "imported": True,
        "destination_must_be_empty": not merge,
        "search_indexes_require_rebuild": True,
    }
