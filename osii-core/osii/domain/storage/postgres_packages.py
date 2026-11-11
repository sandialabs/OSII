"""Explicit portable package exchange; never a runtime filesystem projection."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import tempfile
import zipfile

import tomli_w

from osii.domain.osii_packages import (
    PACKAGE_FORMAT,
    PACKAGE_VERSION,
    MAX_ARCHIVE_BYTES,
    MAX_FILE_COUNT,
    _load_and_validate,
    import_package,
)
from osii.domain.read.postgres import PostgresLibraryReader
from .sidecar_import import plan_import, apply_import
from .sidecar_commits import _toml_value


def export_collection(library, collection_id):
    files = {}

    def put(path, content):
        files[path] = content.encode("utf-8") if isinstance(content, str) else content
        if (
            len(files) > MAX_FILE_COUNT
            or sum(len(value) for value in files.values()) > MAX_ARCHIVE_BYTES
        ):
            raise ValueError(
                "Collection exceeds the portable package safety limit; choose a smaller collection"
            )

    def json_file(path, value):
        put(path, json.dumps(value, ensure_ascii=False))

    def toml_file(path, value):
        put(path, tomli_w.dumps(_toml_value(value)))

    with library.engine.begin() as conn:
        library.sql(conn, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        record = (
            library.sql(
                conn, "SELECT * FROM collections WHERE id=:id", id=collection_id
            )
            .mappings()
            .first()
        )
        if record is None:
            raise KeyError("Collection not found")
        reader = PostgresLibraryReader(library.engine, connection=conn)
        ids = record["members"]
        # Preserve imported attachments/legacy descriptors, then overlay current
        # canonical database representations and complete revision manifests.
        prefixes = [f"objects/{fid}/" for fid in ids] + [
            f"collections/{collection_id}/"
        ]
        total = library.sql(
            conn,
            """SELECT COALESCE(sum(octet_length(content)),0) FROM import_files f
            WHERE EXISTS(SELECT 1 FROM jsonb_array_elements_text(CAST(:prefixes AS jsonb)) p
            WHERE left(f.path,length(p))=p)""",
            prefixes=json.dumps(prefixes),
        ).scalar()
        if total > MAX_ARCHIVE_BYTES:
            raise ValueError("Imported attachments exceed the package safety limit")
        for row in library.sql(
            conn,
            """SELECT DISTINCT ON(f.path) f.path,f.content FROM import_files f
            JOIN settings s ON s.id='sidecar_import:'||f.import_id
            WHERE EXISTS(SELECT 1 FROM jsonb_array_elements_text(CAST(:prefixes AS jsonb)) p
            WHERE left(f.path,length(p))=p)
            ORDER BY f.path,s.value->>'completed_at' DESC""",
            prefixes=json.dumps(prefixes),
        ).mappings():
            put(row["path"], bytes(row["content"]))
        collection_prefix = f"collections/{collection_id}"
        saved = (
            library.sql(
                conn,
                "SELECT value FROM settings WHERE id=:id",
                id="collection_metadata:" + collection_id,
            ).scalar()
            or {}
        )
        toml_file(
            collection_prefix + "/collection.toml",
            {
                "collection": {
                    **{
                        k: saved[k]
                        for k in ("kind", "color", "created_utc", "updated_utc")
                        if k in saved
                    },
                    "id": collection_id,
                    "name": record["name"],
                    "description": record["description"],
                    "kind": saved.get("kind", "manual"),
                }
            },
        )
        put(
            collection_prefix + "/members.jsonl",
            "\n".join(json.dumps({"file_id": fid}) for fid in ids) + "\n",
        )
        objects = []
        for file_id in ids:
            doc = reader.get_document(file_id)
            if doc is None:
                raise ValueError("Collection references an unavailable document")
            prefix = f"objects/{file_id}"
            meta = {
                k: v
                for k, v in doc.metadata.items()
                if k
                not in {
                    "segments",
                    "edited_representation",
                    "edited_text_history",
                    "inventory_links",
                }
            }
            meta.update(
                file={
                    **meta.get("file", {}),
                    "filename": doc.filename,
                    "source_relpath": doc.source_relpath,
                    "mime": doc.media_type,
                    "size_bytes": doc.size_bytes,
                },
                hash={"sha256": doc.sha256},
            )
            toml_file(prefix + "/meta.toml", meta)
            canonical = reader.get_representation(file_id, "canonical")
            put(prefix + "/text.txt", canonical.text)
            segments = [
                {
                    "id": s.segment_id,
                    "kind": "text",
                    "path": "text.txt",
                    "span": {"char_start": s.char_start, "char_end": s.char_end},
                    "source_origin": s.source_origin,
                }
                for s in canonical.segments
            ]
            provenance = {**canonical.provenance, "provenance": {"status": "done"}}
            toml_file(prefix + "/provenance.toml", provenance)
            index = {
                "primary_id": doc.metadata.get("primary_extraction_id"),
                "variants": [],
            }
            for row in library.sql(
                conn,
                "SELECT * FROM extractions WHERE file_id=:id ORDER BY created_at,id",
                id=file_id,
            ).mappings():
                representation = reader.get_representation(file_id, row["id"])
                directory = prefix + "/extractions/" + row["id"]
                put(directory + "/text.txt", representation.text)
                manifest = [
                    {
                        "id": s.segment_id,
                        "kind": "text",
                        "path": "text.txt",
                        "span": {"char_start": s.char_start, "char_end": s.char_end},
                        "source_origin": s.source_origin,
                    }
                    for s in representation.segments
                ]
                for artifact in row["response"].get("artifacts", []):
                    extension = (
                        mimetypes.guess_extension(artifact["media_type"]) or ".bin"
                    )
                    filename = (
                        "artifacts/"
                        + hashlib.sha256(artifact["id"].encode()).hexdigest()[:20]
                        + extension
                    )
                    data = (
                        base64.b64decode(artifact["data_base64"])
                        if artifact.get("data_base64") is not None
                        else (
                            artifact["text"].encode()
                            if artifact.get("text") is not None
                            else json.dumps(
                                artifact.get("standard_data")
                                or artifact.get("json_data")
                            ).encode()
                        )
                    )
                    put(directory + "/" + filename, data)
                    entry = {
                        "id": artifact["id"],
                        "kind": artifact["kind"],
                        "type": artifact["media_type"],
                        "path": filename,
                        "source_origin": artifact.get("source_origin", {}),
                    }
                    manifest.append(entry)
                    if row["id"] == index["primary_id"]:
                        put(prefix + "/" + filename, data)
                        segments.append(entry)
                put(
                    directory + "/manifest.jsonl",
                    "\n".join(json.dumps(s) for s in manifest) + "\n",
                )
                toml_file(
                    directory + "/provenance.toml",
                    {
                        **representation.provenance,
                        "extractor": row["response"].get("processor", {}),
                        "provenance": {"status": "done"},
                    },
                )
                index["variants"].append(
                    {
                        "id": row["id"],
                        "created_utc": row["created_at"].isoformat(),
                        "extractor": row["response"].get("processor", {}),
                        "status": "done",
                        "text_chars": len(representation.text),
                        "manifest_records": len(manifest),
                        "text_sha256": hashlib.sha256(
                            representation.text.encode()
                        ).hexdigest(),
                    }
                )
            json_file(prefix + "/extractions/index.json", index)
            # Current extraction artifacts are data too, not just attachments
            # inside a historical variant. Preserve bytes and source geometry.
            for artifact in reader.artifact_responses(file_id):
                content = reader.get_artifact(file_id, artifact["id"], max_bytes=None)
                payload = artifact["payload"]
                saved = Path(str(payload.get("id", "")))
                relative = (
                    saved.as_posix()
                    if len(saved.parts) > 1
                    and saved.parts[0] == "artifacts"
                    and ".." not in saved.parts
                    and "\\" not in str(saved)
                    else "artifacts/"
                    + hashlib.sha256(artifact["id"].encode()).hexdigest()[:24]
                    + (mimetypes.guess_extension(content.artifact.media_type) or ".bin")
                )
                put(prefix + "/" + relative, content.data)
                segments.append(
                    {
                        "id": artifact["id"],
                        "kind": "image"
                        if content.artifact.media_type.startswith("image/")
                        else artifact["kind"],
                        "path": relative,
                        "type": content.artifact.media_type,
                        "source_origin": payload.get("source_origin", {}),
                    }
                )
            put(
                prefix + "/manifest.jsonl",
                "\n".join(json.dumps(s) for s in segments) + "\n",
            )
            edited = doc.metadata.get("edited_representation")
            if edited:
                json_file(
                    prefix + "/edited_text.json",
                    {"revision": edited["revision"], "segments": edited["segments"]},
                )
            else:
                files.pop(prefix + "/edited_text.json", None)
            if doc.metadata.get("edited_text_history"):
                json_file(
                    prefix + "/edited_text.history.json",
                    doc.metadata["edited_text_history"],
                )
            gov = library.sql(
                conn,
                "SELECT value FROM settings WHERE id=:id",
                id="governance:" + file_id,
            ).scalar() or {"sensitivity_labels": [], "tags": [], "handling_notes": ""}
            toml_file(prefix + "/governance.toml", {"governance": gov})
            context = library.sql(
                conn,
                "SELECT value FROM settings WHERE id=:id",
                id="expert-context:object:" + file_id,
            ).scalar()
            if context:
                put(prefix + "/expert-context.md", context)
            objects.append({"file_id": file_id, "governance": gov})
        products = library.sql(
            conn,
            """SELECT * FROM scope_products WHERE
            (scope_type='collection' AND scope_id=:collection) OR
            (scope_type='object' AND scope_id IN(SELECT jsonb_array_elements_text(CAST(:ids AS jsonb))))""",
            collection=collection_id,
            ids=json.dumps(ids),
        ).mappings()
        for product in products:
            prefix = (
                f"collections/{collection_id}"
                if product["scope_type"] == "collection"
                else f"objects/{product['scope_id']}"
            )
            family = "syntheses" if product["family"] == "synthesis" else "enrichments"
            filename = product["filename"]
            if filename == "current" and product["scope_type"] == "object":
                path = prefix + "/synth.txt"
            else:
                filename = (
                    filename
                    if product["family"] != "synthesis" or filename.endswith(".txt")
                    else filename + ".txt"
                )
                path = prefix + "/" + family + "/" + filename
            revisions = [
                {
                    "id": r["id"],
                    "parent": r["parent"],
                    "origin": r["origin"],
                    "created_at": r["created_at"],
                    "actor_id": r["actor_id"],
                    "data": r["data"],
                    "provenance": r["provenance"],
                }
                for r in library.sql(
                    conn,
                    "SELECT * FROM scope_revisions WHERE product_id=:id ORDER BY created_at,id",
                    id=product["id"],
                ).mappings()
            ]
            if product["family"] == "synthesis":
                for revision in revisions:
                    data = revision["data"]
                    revision["data"] = {
                        "artifact_type": "text",
                        "title": data.get("title", "Summary"),
                        "text": data.get("text") or data.get("markdown") or "",
                        "citations": data.get("citations", []),
                    }
            history_path = (
                str(Path(path).parent.as_posix())
                + "/.history/"
                + hashlib.sha256(Path(path).name.encode()).hexdigest()
                + "/manifest.json"
            )
            json_file(
                history_path,
                {
                    "filename": Path(path).name,
                    "current": product["current_revision"],
                    "revisions": revisions,
                },
            )
            active = next(
                (r for r in revisions if r["id"] == product["current_revision"]), None
            )
            if active:
                if family == "syntheses" or filename == "current":
                    put(
                        path,
                        active["data"].get("text")
                        or active["data"].get("markdown")
                        or "",
                    )
                else:
                    json_file(path, active["data"])
            else:
                files.pop(path, None)
        manifest = {
            "format": PACKAGE_FORMAT,
            "version": PACKAGE_VERSION,
            "package_type": "collection",
            "created_utc": datetime.now(UTC).isoformat(),
            "source_files_included": False,
            "collection": {"id": collection_id, "name": record["name"]},
            "objects": objects,
            "files": [
                {
                    "path": path,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for path, data in sorted(files.items())
            ],
        }
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(files.items()):
                archive.writestr(path, data)
            archive.writestr("osii-package.json", json.dumps(manifest))
        return output.getvalue()


def import_collection(library, content):
    manifest, files = _load_and_validate(content)
    # Reuse existing package validation, including declared scope/ID checks, in
    # scratch space only. It never sees a live sidecar or the source directory.
    with tempfile.TemporaryDirectory(prefix="osii-package-check-") as temporary:
        import_package(Path(temporary), content)
    with tempfile.TemporaryDirectory(prefix="osii-package-import-") as temporary:
        root = Path(temporary)
        for relative, data in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        report = apply_import(library.engine, plan_import(root), merge=True)
    return {
        "ok": True,
        "collection_id": manifest["collection"]["id"],
        "imported_file_ids": [r["file_id"] for r in manifest["objects"]],
        "duplicate_file_ids": [],
        "governance_merged_file_ids": [r["file_id"] for r in manifest["objects"]],
        "indexes_rebuild_required": True,
        "source_files_included": False,
        "import": report,
    }
