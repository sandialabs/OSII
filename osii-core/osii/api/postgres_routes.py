"""Local Workbench HTTP compatibility over explicitly selected PostgreSQL ports.

This is not the hosted server: there are no user accounts, sessions, or roles.
The normal local launcher binds the API to loopback for either backend.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
import time
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from osii.domain.read.contracts import ReadScope, cursor_encode, cursor_decode
from osii.domain.storage.authoring import AuthoringConflict, ProductRef
from osii.domain.storage.retrieval import RetrievalRequest

router = APIRouter()


def library(request):
    return request.app.state.postgres_library


def workflow(request):
    return request.app.state.postgres_workflow


def source_file(request, file_id):
    doc = library(request).reader.get_document(file_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    shared = request.app.state.shared_volume_root.resolve()
    uploads = request.app.state.upload_originals_root.resolve()
    from osii.domain.artifacts.source_files import _resolve_from_root
    from osii.domain.storage.ids import compute_file_id

    target = _resolve_from_root(shared, doc.source_relpath) or _resolve_from_root(
        uploads, doc.source_relpath
    )
    hint = doc.metadata.get("source_absolute_path") or doc.metadata.get("meta", {}).get(
        "source_path"
    )
    if (
        target is None
        and hint
        and getattr(request.app.state, "filesystem_mode", "local") == "local"
    ):
        candidate = Path(hint).resolve()
        if candidate.is_file():
            target = candidate
    if target is None or not target.is_file():
        raise HTTPException(
            404,
            "Original file is unavailable; reconnect its drive or rescan moved sources",
        )
    if compute_file_id(target) != file_id:
        raise HTTPException(
            409,
            "Original file contents changed; rescan and process the changed source before viewing it as this document",
        )
    return target


@router.get("/api/workbench/home")
def home(request: Request):
    from osii.domain.workbench import home_state
    from osii.rag.config import get_chat_settings

    lib = library(request)
    counts = lib.query("""SELECT count(*) AS documents,
        count(*) FILTER(WHERE length(COALESCE(metadata->'edited_representation'->>'text',text))>0) AS texts,
        count(*) FILTER(WHERE metadata ? 'embedding_identity' AND metadata->'embedding_identity'->>'provider'<>'local.hashing'
            AND EXISTS(SELECT 1 FROM chunks c WHERE c.file_id=documents.file_id AND c.embedding IS NOT NULL)
            AND NOT COALESCE((metadata->'stale'->>'embeddings')::boolean,false)) AS indexed
        FROM documents WHERE active""")[0]
    settings = get_chat_settings(lib.backend.root)
    primary = settings.chat_provider_chain[0]
    configured = (
        primary == "ollama"
        and bool(settings.ollama_chat_model)
        or primary == "openai"
        and bool(settings.openai_chat_model)
    )
    return home_state(
        documents=counts["documents"],
        text_documents=counts["texts"],
        indexed_documents=counts["indexed"],
        chat_configured=configured,
        index_ready=bool(counts["indexed"]),
        setup_dismissed=bool(lib.setting("setup_dismissed", False)),
    )


@router.post("/api/admin/setup/dismiss")
def dismiss_setup(request: Request):
    library(request).set_setting("setup_dismissed", True)
    return {"setup": {"visible": False}}


@router.get("/api/catalog/status")
def catalog_status(request: Request):
    lib = library(request)
    return {
        "backend": "postgres",
        "status": "ready",
        "valid": True,
        "generation": lib.query("SELECT revision FROM datasets WHERE id='shared'")[0][
            "revision"
        ],
    }


@router.post("/api/catalog/rebuild")
def rebuild_catalog(request: Request):
    raise HTTPException(
        409,
        "PostgreSQL is authoritative, not a rebuildable sidecar catalog. No data was changed.",
    )


@router.get("/api/catalog/files")
def files(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = None,
    status: str | None = None,
    suffix: str | None = None,
    path: str | None = None,
    text: str | None = None,
):
    lib = library(request)
    suffix = "." + suffix.lstrip(".") if suffix else None
    context = json.dumps(["local-pg-files", status, suffix, path, text])
    after = cursor_decode(cursor, context, 2)
    terms, values = ["active"], {"limit": limit + 1}
    if status and status not in {"done", "partial"}:
        terms.append("false")
    for column, value, mode in (
        ("source_relpath", path, "prefix"),
        ("filename", suffix, "suffix"),
        ("source_relpath", text, "contains"),
    ):
        if value:
            key = f"filter{len(values)}"
            # Literal substring matching, not SQL LIKE patterns.
            terms.append(
                f"{'right' if mode == 'suffix' else 'left' if mode == 'prefix' else 'strpos'}(lower({column}),{'length(:' + key + ')' if mode != 'contains' else ':' + key}) {'=' if mode != 'contains' else '>'} {':' + key if mode != 'contains' else '0'}"
            )
            values[key] = value.lower()
    where = " AND ".join(terms)
    total = lib.query(
        f"SELECT count(*) AS total FROM documents WHERE {where}", **values
    )[0]["total"]
    if after:
        where += ' AND (source_relpath COLLATE "C",file_id COLLATE "C") > (:after_path,:after_id)'
        values.update(after_path=after[0], after_id=after[1])
    rows = lib.query(
        f'SELECT file_id,source_relpath,filename,media_type AS mime,size_bytes,sha256,updated_at FROM documents WHERE {where} ORDER BY source_relpath COLLATE "C",file_id COLLATE "C" LIMIT :limit',
        **values,
    )
    items = [
        {**row, "status": "done", "suffix": Path(row["filename"]).suffix.lower()}
        for row in rows[:limit]
    ]
    next_cursor = (
        cursor_encode(context, [items[-1]["source_relpath"], items[-1]["file_id"]])
        if len(rows) > limit
        else None
    )
    return {"items": items, "total": total, "limit": limit, "next_cursor": next_cursor}


@router.get("/api/catalog/folders")
def folders(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = None,
    path: str | None = None,
    text: str | None = None,
):
    rows = [
        row
        for row in library(request).folders()
        if (not path or row["path"].startswith(path))
        and (not text or text.casefold() in row["path"].casefold())
    ]
    context = json.dumps(["pg-folders", path, text])
    after = cursor_decode(cursor, context, 2)
    total = len(rows)
    if after:
        rows = [row for row in rows if (row["path"], row["folder_id"]) > tuple(after)]
    selected = rows[:limit]
    return {
        "items": selected,
        "total": total,
        "limit": limit,
        "next_cursor": cursor_encode(
            context, [selected[-1]["path"], selected[-1]["folder_id"]]
        )
        if len(rows) > limit
        else None,
    }


@router.post("/api/objects/summaries")
def summaries(request: Request, payload: dict):
    ids = payload.get("file_ids", [])
    if not isinstance(ids, list) or len(ids) > 10000:
        raise HTTPException(422, "file_ids must be a list of at most 10,000 IDs")
    return {"summaries": library(request).summaries(ids)}


@router.get("/api/objects/{file_id}")
def document(request: Request, file_id: str):
    lib = library(request)
    scope = {"scope_type": "object", "file_id": file_id}
    meta, records = lib.meta(file_id), lib.manifest(file_id)
    summary = lib.summaries([file_id])[0]
    representations = texts(request, file_id)["representations"]
    artifacts = {
        "has_extraction": True,
        "has_synthesis": summary["has_synthesis"],
        "has_enrichments": summary["has_enrichments"],
        "manifest_record_count": len(records),
        "text_representations": representations,
        "syntheses": lib.syntheses(scope),
        "enrichments": lib.enrichments(scope),
    }
    return {
        "file_id": file_id,
        "meta": meta,
        "processing": lib.processing(file_id),
        "collections": summary["collections"],
        "enrichments": artifacts["enrichments"],
        "governance": lib.setting(
            "governance:" + file_id,
            {
                "sensitivity_labels": [],
                "tags": [],
                "handling_notes": "",
                "updated_utc": None,
            },
        ),
        "overview": {
            "file_id": file_id,
            "meta": meta,
            "text_count": sum(r["kind"] == "text" for r in records),
            "image_count": sum(r["kind"] == "image" for r in records),
            "has_synth": summary["has_synthesis"],
            "text_items": [r for r in records if r["kind"] == "text"],
            "image_items": [r for r in records if r["kind"] == "image"],
        },
        "artifact_summary": {
            "file_id": file_id,
            "source_state": summary["source_state"],
            "artifacts": artifacts,
            "actions": {
                "can_extract": True,
                "can_synthesize": True,
                "can_enrich": True,
                "source_is_active": True,
            },
        },
    }


@router.get("/api/objects/{file_id}/source")
def source(request: Request, file_id: str):
    return FileResponse(source_file(request, file_id))


@router.get("/api/objects/{file_id}/manifest")
def manifest(request: Request, file_id: str):
    return {"file_id": file_id, "records": library(request).manifest(file_id)}


@router.get("/api/objects/{file_id}/texts")
def texts(request: Request, file_id: str):
    doc = library(request).reader.get_document(file_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    edited = doc.metadata.get("edited_representation") is not None
    return {
        "file_id": file_id,
        "segments": library(request).manifest(file_id),
        "representations": [
            {
                "name": "canonical",
                "kind": "canonical_extracted_text",
                "path": f"objects/{file_id}/text.txt",
                "exists": True,
                "preferred": not edited,
            },
            {
                "name": "edited",
                "kind": "edited_text",
                "path": f"objects/{file_id}/edited_text.json",
                "exists": edited,
                "preferred": edited,
            },
        ],
    }


@router.get("/api/objects/{file_id}/texts/preferred")
def preferred(request: Request, file_id: str):
    record = library(request).reader.get_representation(file_id)
    if record is None:
        raise HTTPException(404, "Document text not found")
    edited = record.kind == "edited_text"
    return {
        "file_id": file_id,
        "representation": "edited" if edited else "canonical",
        "kind": record.kind,
        "text": record.text,
        "path": f"objects/{file_id}/{'edited_text.json' if edited else 'text.txt'}",
    }


@router.get("/api/objects/{file_id}/texts/edited")
def edited_text(request: Request, file_id: str):
    record = library(request).backend.text.get(file_id)
    return {
        "file_id": file_id,
        "exists": record.revision is not None,
        "revision": record.revision,
        "representation": "edited",
        "segments": record.segments,
    }


@router.put("/api/objects/{file_id}/texts/edited")
def edit_text(request: Request, file_id: str, payload: dict):
    editor = library(request).backend.text
    if not isinstance(payload.get("segments"), list):
        raise HTTPException(422, "segments must be a list")
    # Existing Workbench clients predate optimistic text tokens. New clients
    # send expected_revision; old callers retain their documented last-write behavior.
    current = editor.get(file_id)
    record = editor.save(
        file_id,
        payload["segments"],
        expected_revision=payload.get("expected_revision", current.revision),
    )
    return {
        "file_id": file_id,
        "representation": "edited",
        "updated": True,
        "revision": record.revision,
        "segments": record.segments,
        "stale": {"embeddings": True, "search_chunks": True},
    }


@router.delete("/api/objects/{file_id}/texts/edited")
def delete_edit(request: Request, file_id: str):
    editor = library(request).backend.text
    current = editor.get(file_id)
    editor.save(file_id, None, expected_revision=current.revision)
    return {
        "file_id": file_id,
        "representation": "edited",
        "removed": current.revision is not None,
        "stale": {"embeddings": True, "search_chunks": True},
    }


@router.get("/api/text/objects/{file_id}/span")
@router.get("/api/text/objects/{file_id}/span/context")
def text_span(
    request: Request,
    file_id: str,
    char_start: int,
    char_end: int,
    context_chars: int = 200,
):
    record = library(request).reader.get_representation(file_id, "canonical")
    if record is None or not 0 <= char_start <= char_end <= len(record.text):
        raise HTTPException(422, "Invalid canonical text span")
    context_chars = max(0, min(context_chars, 4000))
    return {
        "file_id": file_id,
        "char_start": char_start,
        "char_end": char_end,
        "text": record.text[char_start:char_end],
        "match_text": record.text[char_start:char_end],
        "before_text": record.text[max(0, char_start - context_chars) : char_start],
        "after_text": record.text[char_end : char_end + context_chars],
        "context_start": max(0, char_start - context_chars),
        "context_end": min(len(record.text), char_end + context_chars),
        "window_start": max(0, char_start - context_chars),
        "window_end": min(len(record.text), char_end + context_chars),
    }


@router.get("/api/objects/{file_id}/extractions")
def extractions(request: Request, file_id: str):
    lib = library(request)
    doc = lib.reader.get_document(file_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    rows = lib.query(
        "SELECT id,response,created_at FROM extractions WHERE file_id=:id ORDER BY created_at,id",
        id=file_id,
    )
    return {
        "file_id": file_id,
        "primary_id": doc.metadata.get("primary_extraction_id"),
        "variants": [
            {
                "id": row["id"],
                "created_utc": row["created_at"],
                "extractor": row["response"]["processor"],
                "status": "done",
                "text_chars": len(
                    lib.reader.get_representation(file_id, row["id"]).text
                ),
                "manifest_records": len(row["response"].get("segments", [])),
                "primary": row["id"] == doc.metadata.get("primary_extraction_id"),
                "text_path": f"extractions/{row['id']}/text",
                "manifest_path": f"extractions/{row['id']}/manifest",
                "provenance_path": f"extractions/{row['id']}/provenance",
            }
            for row in rows
        ],
    }


@router.get("/api/objects/{file_id}/extractions/{variant_id}/texts")
def extraction_text(request: Request, file_id: str, variant_id: str):
    record = library(request).reader.get_representation(file_id, variant_id)
    if record is None:
        raise HTTPException(404, "Extraction not found")
    return {
        "file_id": file_id,
        "extraction_id": record.representation_id,
        "text": record.text,
        "segments": [
            {
                "id": s.segment_id,
                "kind": "text",
                "span": {"char_start": s.char_start, "char_end": s.char_end},
                "source_origin": s.source_origin,
            }
            for s in record.segments
        ],
    }


@router.get("/api/objects/{file_id}/extractions/{variant_id}/artifacts")
def extraction_artifacts(request: Request, file_id: str, variant_id: str):
    rows = library(request).query(
        "SELECT response FROM extractions WHERE id=:id AND file_id=:file",
        id=variant_id,
        file=file_id,
    )
    if not rows:
        raise HTTPException(404, "Extraction not found")
    return {
        "file_id": file_id,
        "variant_id": variant_id,
        "artifacts": [
            {
                "id": row["id"],
                "kind": row["kind"],
                "media_type": row["media_type"],
                "source_origin": row.get("source_origin", {}),
                "filename": row["id"],
                "size_bytes": None,
                "data": row.get("standard_data") or row.get("json_data"),
            }
            for row in rows[0]["response"].get("artifacts", [])
        ],
    }


@router.post("/api/objects/{file_id}/extractions")
def queue_extraction(request: Request, file_id: str, payload: dict):
    source = source_file(request, file_id)
    options = {
        "run_extraction": True,
        "extract_mode": "reprocess",
        "extraction_policy": payload.get("extraction_policy", "save_variant"),
        "extractor_overrides": {source.suffix.lower(): payload["extractor_name"]},
        "workflow": "library",
        "expected_file_ids": {str(source): file_id},
    }
    job = workflow(request).submit_files(
        [source],
        options,
        shared_root=request.app.state.shared_volume_root,
        upload_root=request.app.state.upload_originals_root,
    )
    return workflow(request).run_view(job)


@router.get("/api/objects/{file_id}/syntheses")
def syntheses(request: Request, file_id: str):
    scope = {"scope_type": "object", "file_id": file_id}
    lib = library(request)
    return {
        "file_id": file_id,
        "current_text": lib.synthesis(scope),
        "current_toml": None,
        "syntheses": lib.syntheses(scope),
    }


@router.get("/api/collections")
def collections(request: Request):
    lib = library(request)
    return {
        "collections": [
            lib.collection_view(row) for row in lib.backend.collections.list()
        ]
    }


@router.post("/api/collections")
def create_collection(request: Request, payload: dict):
    lib = library(request)
    row = lib.backend.collections.create(
        payload.get("name", ""), description=payload.get("description")
    )
    from datetime import UTC, datetime

    created = datetime.now(UTC).isoformat()
    lib.set_setting(
        "collection_metadata:" + row.collection_id,
        {
            "color": payload.get("color"),
            "kind": payload.get("kind", "manual"),
            "created_utc": created,
            "updated_utc": created,
        },
    )
    return {"collection": lib.collection_view(row)}


@router.get("/api/collections/{collection_id}")
def collection(request: Request, collection_id: str):
    lib = library(request)
    row = lib.backend.collections.get(collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")
    return {
        "collection": lib.collection_view(row),
        "artifact_summary": collection_artifacts(request, collection_id),
    }


@router.patch("/api/collections/{collection_id}")
def update_collection(request: Request, collection_id: str, payload: dict):
    lib = library(request)
    previous = lib.backend.collections.get(collection_id)
    if previous is None:
        raise HTTPException(404, "Collection not found")
    row = lib.backend.collections.update(
        collection_id,
        expected_version=payload.get("expected_version", previous.version),
        name=payload.get("name"),
        description=payload.get("description"),
    )
    from datetime import UTC, datetime

    meta = lib.setting("collection_metadata:" + collection_id, {})
    lib.set_setting(
        "collection_metadata:" + collection_id,
        {
            **meta,
            **{k: payload[k] for k in ("kind", "color") if k in payload},
            "updated_utc": datetime.now(UTC).isoformat(),
        },
    )
    return {"collection": lib.collection_view(row)}


@router.get("/api/collections/{collection_id}/members")
def members(request: Request, collection_id: str):
    lib = library(request)
    row = lib.backend.collections.get(collection_id)
    if row is None:
        raise HTTPException(404, "Collection not found")
    return {"collection": lib.collection_view(row), "file_ids": row.member_ids}


@router.post("/api/collections/{collection_id}/members")
def add_members(request: Request, collection_id: str, payload: dict):
    lib = library(request)
    previous = lib.backend.collections.get(collection_id)
    if previous is None:
        raise HTTPException(404, "Collection not found")
    ids = payload.get("file_ids", [])
    if not isinstance(ids, list):
        raise HTTPException(422, "file_ids must be a list")
    if any(lib.reader.get_document(i) is None for i in ids):
        raise HTTPException(422, "Unknown document in selection")
    row = lib.backend.collections.replace_members(
        collection_id,
        (*previous.member_ids, *ids),
        expected_version=payload.get("expected_version", previous.version),
    )
    return {
        "collection": lib.collection_view(row),
        "file_ids": row.member_ids,
        "added": list(set(ids) - set(previous.member_ids)),
    }


@router.delete("/api/collections/{collection_id}/members/{file_id}")
def remove_member(request: Request, collection_id: str, file_id: str):
    lib = library(request)
    previous = lib.backend.collections.get(collection_id)
    if previous is None:
        raise HTTPException(404, "Collection not found")
    row = lib.backend.collections.replace_members(
        collection_id,
        [i for i in previous.member_ids if i != file_id],
        expected_version=previous.version,
    )
    return {
        "collection": lib.collection_view(row),
        "file_ids": row.member_ids,
        "removed": file_id,
    }


@router.delete("/api/collections/{collection_id}")
def delete_collection(request: Request, collection_id: str):
    lib = library(request)
    with lib.engine.begin() as conn:
        row = lib.sql(
            conn, "SELECT id FROM collections WHERE id=:id FOR UPDATE", id=collection_id
        ).first()
        if row is None:
            raise HTTPException(404, "Collection not found")
        lib.sql(
            conn,
            "DELETE FROM scope_products WHERE scope_type='collection' AND scope_id=:id",
            id=collection_id,
        )
        lib.sql(conn, "DELETE FROM collections WHERE id=:id", id=collection_id)
        lib.sql(
            conn,
            "DELETE FROM settings WHERE id=:id",
            id="collection_metadata:" + collection_id,
        )
        lib.sql(
            conn,
            "DELETE FROM import_files WHERE left(path,length(:prefix))=:prefix",
            prefix=f"collections/{collection_id}/",
        )
        lib.sql(
            conn,
            "UPDATE settings SET value=value||jsonb_build_object('invalidated_by_deletion',true) WHERE id='sidecar_import' OR left(id,15)='sidecar_import:'",
        )
    return {"ok": True}


@router.post("/api/scopes/describe")
def describe_scope(request: Request, payload: dict):
    lib = library(request)
    return {
        "scope": lib.describe(payload),
        "member_file_ids": [d.file_id for d in lib.documents(payload)],
    }


@router.get("/api/scopes/root")
def root_scope(request: Request):
    return describe_scope(request, {"scope_type": "root"})


@router.get("/api/scopes/folders")
def folder_scopes(request: Request):
    lib = library(request)
    return {
        "scopes": [
            lib.describe({"scope_type": "folder", "folder_id": row["folder_id"]})
            for row in lib.folders()
        ]
    }


@router.get("/api/scopes/collections")
def collection_scopes(request: Request):
    lib = library(request)
    return {
        "scopes": [
            lib.describe(
                {"scope_type": "collection", "collection_id": row.collection_id}
            )
            for row in lib.backend.collections.list()
        ]
    }


@router.post("/api/scopes/summaries")
def scope_summaries(request: Request, payload: dict):
    scope = payload.get("scope") or payload
    lib = library(request)
    return {
        "scope": scope,
        "summaries": lib.summaries([d.file_id for d in lib.documents(scope)]),
    }


@router.post("/api/scopes/overview")
def scope_overview(request: Request, payload: dict):
    return library(request).overview(payload.get("scope") or payload)


@router.post("/api/scopes/artifacts")
def scope_artifacts(request: Request, payload: dict):
    return library(request).artifact_summary(payload.get("scope") or payload)


@router.post("/api/enrichments/list")
def enrichment_list(request: Request, payload: dict):
    return {"scope": payload, "enrichments": library(request).enrichments(payload)}


@router.post("/api/enrichments/payload")
def enrichment_payload(request: Request, payload: dict):
    lib = library(request)
    row = next(
        (
            r
            for r in lib.product_rows(payload["scope"])
            if r["filename"] == payload["filename"]
        ),
        None,
    )
    if row is None:
        raise HTTPException(404, "Product not found")
    return {
        "scope": payload["scope"],
        "filename": row["filename"],
        "data": row["data"],
        "metadata": row["provenance"],
    }


@router.get("/api/enrichments/objects/{file_id}/{filename}")
def object_enrichment(request: Request, file_id: str, filename: str):
    return enrichment_payload(
        request,
        {"scope": {"scope_type": "object", "file_id": file_id}, "filename": filename},
    )


@router.post("/api/products/list")
def product_list(request: Request, payload: dict):
    lib = library(request)
    return {
        "products": [
            lib.product_view(payload, row) for row in lib.product_rows(payload)
        ]
    }


@router.post("/api/products/revisions")
@router.post("/api/enrichments/revisions")
def product_history(request: Request, payload: dict):
    return library(request).history(payload)


@router.put("/api/products/revisions")
@router.put("/api/enrichments/revisions")
def edit_product(request: Request, payload: dict):
    lib = library(request)
    if "expected_revision" not in payload:
        raise HTTPException(422, "expected_revision is required")
    ref = lib.product_ref(payload)
    if payload.get("revision"):
        lib.backend.products.activate(
            ref, payload["revision"], expected_revision=payload["expected_revision"]
        )
    else:
        data = payload.get("data")
        if data is None:
            data = {**lib.history(payload)["data"], "markdown": payload["markdown"]}
        lib.backend.products.save(
            ref, data, expected_revision=payload["expected_revision"], activate=True
        )
    return lib.history(payload)


@router.post("/api/search")
def search(request: Request, payload: dict):
    lib = library(request)
    found = lib.retrieve(
        RetrievalRequest(
            payload.get("query", ""),
            lib.scope(payload.get("scope") or {}),
            payload.get("mode", "hybrid"),
            payload.get("top_k", 10),
            group_by=payload.get("group_by"),
        )
    )
    return {
        **found.metadata,
        "top_k": found.request.top_k,
        "scope": payload.get("scope") or {"scope_type": "root"},
        "group_by": found.request.group_by,
        "results": found.legacy_rows(),
    }


@router.get("/api/search")
def search_get(request: Request, q: str, top_k: int = 10):
    return search(request, {"query": q, "top_k": top_k, "mode": "hybrid"})


@router.post("/api/chat")
def chat(request: Request, payload: dict):
    from osii.rag.models import ChatRequest
    from osii.rag.service import answer_question

    parsed = ChatRequest.model_validate(payload)
    if parsed.profile_id != "default":
        from osii.rag.local_experiments import answer_experiment

        return answer_experiment(
            library(request).backend.root,
            parsed,
            library=library(request),
            reranker=request.app.state.rag_reranker,
        )
    return answer_question(
        library(request).backend.root, parsed, retriever=library(request)
    )


@router.post("/api/research/report")
def research(request: Request, payload: dict):
    from osii.domain.research import ReportRequest, write_report
    from osii.rag.config import get_chat_settings
    from osii.rag.generation import run_messages

    lib = library(request)
    settings = get_chat_settings(lib.backend.root)
    provider = settings.chat_provider_chain[0]
    model = (
        settings.ollama_chat_model
        if provider == "ollama"
        else settings.openai_chat_model or settings.chat_model
    )

    def complete(messages):
        return run_messages(
            provider=provider,
            settings=settings,
            model=model,
            messages=messages,
            max_tokens=6000,
        )

    return write_report(
        lib.reader,
        ReportRequest.model_validate(payload),
        None if provider == "extractive" else complete,
        provider=provider,
        model=model if provider != "extractive" else None,
    )


@router.get("/api/runs")
def runs(request: Request):
    flow = workflow(request)
    rows = flow.queue.list()
    heartbeat = library(request).setting("local_worker", {})
    live = time.time() - heartbeat.get("heartbeat", 0) < 15
    return {
        "runs": [flow.run_view(row) for row in rows],
        "queue": [{"id": row.job_id, "status": row.state} for row in rows],
        "worker": {
            "available": live,
            "detail": "PostgreSQL worker running"
            if live
            else "Start the worker with make dev or scripts/osii.ps1 dev",
            "last_heartbeat": None,
        },
    }


@router.get("/api/runs/{run_id}")
def run(request: Request, run_id: str):
    row = workflow(request).queue.get(run_id)
    if row is None:
        raise HTTPException(404, "Run not found")
    return workflow(request).run_view(row)


@router.get("/api/runs/{run_id}/logs")
def run_logs(request: Request, run_id: str):
    row = workflow(request).queue.get(run_id)
    if row is None:
        raise HTTPException(404, "Run not found")
    return {"run_id": run_id, "logs": row.logs}


@router.post("/api/runs/{run_id}/{action}")
def run_control(request: Request, run_id: str, action: str):
    from osii.domain.processing.postgres_workflow import configuration_stamp

    flow = workflow(request)
    if action in {"resume", "retry"}:
        with flow.backend.engine.begin() as conn:
            library(request).sql(
                conn,
                "UPDATE jobs SET payload=payload-'budget_started_at' WHERE id=:id AND status IN('paused','error')",
                id=run_id,
            )
    row = flow.queue.control(
        run_id, action, configuration_stamp=lambda: configuration_stamp(flow.root)
    )
    return {"run_id": row.job_id, "status": row.state, "queue_status": row.state}


@router.post("/api/enrichment-jobs/run")
def enrichment_run(request: Request, payload: dict):
    flow = workflow(request)
    row = flow.submit_scope(
        payload["scope"],
        payload["enricher_name"],
        "enricher",
        payload.get("enricher_config"),
        payload.get("expert_context"),
        payload.get("model_bindings"),
    )
    return {
        "run_id": row.job_id,
        "status": row.state,
        "scope": payload["scope"],
        "enricher_name": payload["enricher_name"],
    }


@router.post("/api/synthesis/objects/{file_id}")
def synthesis_run(request: Request, file_id: str, payload: dict):
    flow = workflow(request)
    row = flow.submit_scope(
        {"scope_type": "object", "file_id": file_id},
        payload["synthesizer_name"],
        "synthesizer",
        payload.get("synthesizer_config"),
        payload.get("expert_context"),
    )
    return {
        "run_id": row.job_id,
        "status": row.state,
        "file_id": file_id,
        "synthesizer_name": payload["synthesizer_name"],
    }


def batch_tasks(request, run_id, task_id=None):
    row = workflow(request).queue.get(run_id)
    if row is None:
        raise HTTPException(404, "Batch run not found")
    tasks = [row.payload] if row.kind == "local-scope" else row.payload.get("tasks", [])
    if task_id is not None:
        tasks = [r for r in tasks if r.get("task_id") == task_id]
    if not tasks:
        raise HTTPException(404, "Batch task not found")
    return tasks


@router.get("/api/enrichment-jobs/runs/{run_id}/batches")
def batches(
    request: Request,
    run_id: str,
    cursor: int = 0,
    limit: int = 20,
    task_id: str | None = None,
):
    tasks = batch_tasks(request, run_id, task_id)
    cursor = max(0, cursor)
    limit = max(1, min(50, limit))
    rows = [r for task in tasks for r in task["batches"]]
    return {
        "items": [
            {k: v for k, v in batch.items() if k not in {"inputs", "result"}}
            | {"status": "done" if batch["result"] else "pending"}
            for batch in rows[cursor : cursor + limit]
        ],
        "total": len(rows),
        "next_cursor": cursor + limit if cursor + limit < len(rows) else None,
        "summary": tasks[0]["batch_progress"] if len(tasks) == 1 else None,
    }


@router.get("/api/enrichment-jobs/runs/{run_id}/batches/{batch_id}")
def batch_result(
    request: Request, run_id: str, batch_id: str, task_id: str | None = None
):
    batch = next(
        (
            b
            for task in batch_tasks(request, run_id, task_id)
            for b in task["batches"]
            if b["id"] == batch_id
        ),
        None,
    )
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return {k: v for k, v in batch.items() if k != "inputs"}


@router.get("/api/enrichment-jobs/runs/{run_id}/sources")
def batch_sources(
    request: Request,
    run_id: str,
    cursor: int = 0,
    limit: int = 50,
    only_missing: bool = False,
    task_id: str | None = None,
):
    sources = [
        r
        for task in batch_tasks(request, run_id, task_id)
        for r in task.get("source_inputs", [])
    ]
    if only_missing:
        sources = [r for r in sources if not r["has_text"]]
    cursor = max(0, cursor)
    limit = max(1, min(100, limit))
    return {
        "items": [
            {k: v for k, v in r.items() if k != "text"}
            for r in sources[cursor : cursor + limit]
        ],
        "total": len(sources),
        "next_cursor": cursor + limit if cursor + limit < len(sources) else None,
    }


def artifact_response(request, file_path):
    lib = library(request)
    parts = file_path.split("/")
    if len(parts) >= 2 and parts[0] == "products":
        rows = lib.query(
            "SELECT r.data,r.provenance,p.family FROM scope_products p JOIN scope_revisions r ON r.id=p.current_revision WHERE p.id=:id",
            id=parts[1],
        )
        if not rows:
            raise HTTPException(404, "Product not found")
        row = rows[0]
        if parts[-1] == "metadata":
            return Response(
                json.dumps(row["provenance"]), media_type="application/json"
            )
        if row["family"] == "synthesis":
            return Response(
                row["data"].get("markdown") or row["data"].get("text") or "",
                media_type="text/plain",
            )
        return Response(json.dumps(row["data"]), media_type="application/json")
    if len(parts) == 3 and parts[0] == "objects" and parts[2] == "text.txt":
        record = lib.reader.get_representation(parts[1], "canonical")
        if record:
            return Response(record.text, media_type="text/plain")
    if len(parts) >= 4 and parts[0] == "objects" and parts[2] == "artifacts":
        content = lib.reader.get_artifact(parts[1], "/".join(parts[3:]), max_bytes=None)
        if content:
            return Response(content.data, media_type=content.artifact.media_type)
    raise HTTPException(404, "Artifact not found")


@router.get("/api/browse")
def browse(
    request: Request,
    path: str | None = None,
    include_patterns: str = "",
    exclude_patterns: str = "",
    show_hidden: bool = False,
):
    from osii.api.intake_routes import resolve_requested_path
    from osii.domain.processing.intake import parse_patterns
    from osii.domain.processing.pathing import display_rel, source_relpath

    shared = request.app.state.shared_volume_root.resolve()
    uploads = request.app.state.upload_originals_root.resolve()
    current = resolve_requested_path(request, path)
    if not current.is_dir():
        raise HTTPException(422, "Choose a folder")
    processed = {
        row["source_relpath"]
        for row in library(request).query(
            "SELECT source_relpath FROM documents WHERE active"
        )
    }
    includes, excludes = (
        parse_patterns(include_patterns),
        parse_patterns(exclude_patterns),
    )
    entries = []
    for child in sorted(
        current.iterdir(), key=lambda p: (p.is_file(), p.name.casefold())
    ):
        if not show_hidden and child.name.startswith("."):
            continue
        is_file = child.is_file()
        rel = (
            child.relative_to(shared).as_posix()
            if child.is_relative_to(shared)
            else child.name
        )
        if is_file and (
            (
                includes
                and not any(fnmatch.fnmatch(rel.lower(), p.lower()) for p in includes)
            )
            or any(fnmatch.fnmatch(rel.lower(), p.lower()) for p in excludes)
        ):
            continue
        entries.append(
            {
                "name": child.name,
                "display": display_rel(child, shared, uploads),
                "path": str(child),
                "type": "file" if is_file else "folder",
                "size_bytes": child.stat().st_size if is_file else None,
                "processed": is_file
                and source_relpath(child, shared.parent) in processed,
            }
        )
    return {
        "current_path": str(current),
        "display_path": display_rel(current, shared, uploads),
        "folder_name": current.name,
        "parent_path": str(current.parent) if current.parent != current else None,
        "filesystem_mode": getattr(request.app.state, "filesystem_mode", "local"),
        "host_path": str(current),
        "entries": entries,
    }


@router.post("/api/resolve")
def resolve(request: Request, payload: dict):
    from osii.api.intake_routes import resolve_requested_path
    from osii.domain.processing.intake import (
        expand_queue_to_files,
        parse_patterns,
        add_extractor_plan,
    )
    from osii.domain.processing.pathing import display_rel, source_relpath

    if payload.get("inventory_selection_id") is not None:
        from osii.volume.staging import staged_bundle, selection_id, selection_preview

        bundle = staged_bundle(
            request.app.state.osii_root,
            selection_id(payload["inventory_selection_id"]),
            store=request.app.state.inventory_store,
        )
        return selection_preview(bundle, payload.get("extractor_overrides"), payload)
    shared = request.app.state.shared_volume_root.resolve()
    uploads = request.app.state.upload_originals_root.resolve()
    queue = []
    paths = [resolve_requested_path(request, p) for p in payload.get("queue_paths", [])]
    for path in paths:
        queue.append(
            {
                "path": str(path),
                "display": display_rel(path, shared, uploads),
                "kind": "folder" if path.is_dir() else "file",
                "source": "shared",
            }
        )

    def patterns(key):
        raw = payload.get(key, "")
        return parse_patterns("\n".join(raw) if isinstance(raw, list) else raw)

    found, preview = expand_queue_to_files(
        queue_items=queue,
        include_subfolders=bool(payload.get("include_subfolders", True)),
        include_patterns=patterns("include_patterns"),
        exclude_patterns=patterns("exclude_patterns"),
        show_hidden=bool(payload.get("show_hidden", False)),
        max_files=int(payload["max_files"]) if payload.get("max_files") else None,
        max_total_size=int(float(payload["max_total_size_mb"]) * 1024 * 1024)
        if payload.get("max_total_size_mb")
        else None,
        shared_root=shared,
        upload_root=uploads,
        excluded_paths=payload.get("excluded_paths", []),
    )
    if getattr(request.app.state, "filesystem_mode", "local") == "mounted":
        for path in found:
            resolve_requested_path(request, str(path))
    known = {
        row["source_relpath"]
        for row in library(request).query(
            "SELECT source_relpath FROM documents WHERE active"
        )
    }
    done = 0
    for row in preview.get("available_files", []):
        row["processed"] = source_relpath(Path(row["path"]), shared.parent) in known
        done += int(row["processed"])
    preview.update(processed_count=done, unprocessed_count=len(found) - done)
    add_extractor_plan(preview, found, payload.get("extractor_overrides") or {})
    return {
        "queue_items": queue,
        "resolved_files": [
            {"path": str(p), "display": display_rel(p, shared, uploads)} for p in found
        ],
        "preview": preview,
    }


@router.post("/api/runs")
def start_run(request: Request, payload: dict):
    selection = resolve(request, payload)
    flow = workflow(request)
    options = dict(payload)
    options["context"] = payload.get("expert_context", payload.get("context"))
    if options["context"] is not None and (
        not isinstance(options["context"], str) or len(options["context"]) > 20000
    ):
        raise ValueError("Expert context must be text of at most 20,000 characters")
    staging = None
    job_id = None
    paths = [row["path"] for row in selection["resolved_files"]]
    if payload.get("inventory_selection_id") is not None:
        from osii.volume.staging import staged_bundle, selection_id, member_path

        store = request.app.state.inventory_store
        sid = selection_id(payload["inventory_selection_id"])
        staging = staged_bundle(request.app.state.osii_root, sid, store=store)
        staging["max_seconds"] = int(payload.get("max_processing_seconds", 3600))
        if not 1 <= staging["max_seconds"] <= 86400:
            raise ValueError(
                "Processing time budget must be between 1 and 86,400 seconds"
            )
        job_id = store.handoff(
            sid,
            {
                "library_id": library(request).library_id,
                "storage_backend": "postgres",
                **payload,
            },
        )
        previous = flow.queue.get(job_id)
        if previous:
            return flow.run_view(previous)
        paths = [member_path(member) for member in staging["members"]]
    if not paths:
        raise ValueError("Choose at least one file to process")
    if payload.get("create_collection") and not payload.get("collection_id"):
        created = create_collection(
            request,
            {
                "name": payload.get("collection_name")
                or payload.get("intake_name")
                or "Intake"
            },
        )
        options["collection_id"] = created["collection"]["id"]
    job = flow.submit_files(
        paths,
        options,
        shared_root=request.app.state.shared_volume_root,
        upload_root=request.app.state.upload_originals_root,
        staging=staging,
        job_id=job_id,
    )
    return {
        **flow.run_view(job),
        "preview": selection["preview"],
        "resolved_count": len(paths),
    }


@router.get("/api/intake/readiness")
def readiness(request: Request):
    from osii.domain.processing.capability_readiness import intake_capability_readiness
    from osii.domain.processing.source_access import source_access_summary

    root = request.app.state.osii_root
    result = intake_capability_readiness(root)
    result["source"] = source_access_summary(
        request.app.state.shared_volume_root,
        root,
        configured_kind=getattr(request.app.state, "source_kind", "auto"),
    )
    result["storage_backend"] = "postgres"
    indexes = library(request).query(
        "SELECT DISTINCT metadata->'embedding_identity' AS identity,metadata->'embedding_provenance'->'processor' AS processor FROM documents WHERE active AND metadata ? 'embedding_identity' AND NOT COALESCE((metadata->'stale'->>'embeddings')::boolean,false)"
    )
    from osii.domain.processing.postgres_workflow import embedding_binding
    from osii.processor_sdk import ProcessorClient

    selected = next(
        (
            item
            for item in result["embedders"]
            if item.get("id") == result["defaults"]["embedder"]
        ),
        {},
    )
    expected = None
    binding = None
    if selected.get("available") and selected.get("base_url"):
        try:
            expected = ProcessorClient(selected["base_url"], timeout=5).descriptor()
            binding = embedding_binding(root, expected, selected["base_url"])
        except Exception:
            pass
    result["semantic_indexes"] = []
    for row in indexes:
        identity = row["identity"]
        model_matches = identity.get("model") == selected.get("model")
        if expected and expected.name == "ollama.embedder":
            from osii.domain.processing.capability_readiness import _model_name_matches

            model_matches = _model_name_matches(
                str(identity.get("model", "")), str(selected.get("model", ""))
            )
        compatible = bool(
            expected
            and (row["processor"] or {}).get("name") == expected.name
            and model_matches
            and identity.get("connection_fingerprint") == binding
        )
        result["semantic_indexes"].append(
            {
                "index_id": hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode()
                ).hexdigest()[:20],
                "provider_id": identity["provider"],
                "model": identity["model"],
                "dimensions": identity["dimensions"],
                "normalized": identity["normalized"],
                "semantic": identity["provider"] != "local.hashing",
                "compatible": compatible,
                "relpath": "postgresql:chunks",
                "created_utc": None,
            }
        )
    compatible_index = next(
        (r for r in result["semantic_indexes"] if r["compatible"]), None
    )
    if selected:
        selected["index_compatible"] = compatible_index is not None
        selected["index_rebuild_required"] = compatible_index is None
        if compatible_index:
            selected["indexed_model"] = compatible_index["model"]
    return result


@router.get("/api/enrichment-jobs/tools")
def tools(request: Request):
    from osii.domain.tool_actions import tool_catalog

    result = tool_catalog(request.app.state.osii_root)
    result["library_id"] = library(request).library_id
    return result


@router.get("/api/osii/files")
def osii_files(request: Request):
    return {
        "files": [
            {"file_id": d.file_id, "source_relpath": d.source_relpath}
            for d in library(request).documents()
        ]
    }


@router.get("/api/osii/folders")
def osii_folders(request: Request):
    return {"folders": library(request).folders()}


@router.get("/api/osii/resolve/file")
def resolve_file(request: Request, source_relpath: str):
    rows = library(request).query(
        "SELECT file_id FROM documents WHERE source_relpath=:path AND active ORDER BY file_id",
        path=source_relpath,
    )
    if not rows:
        raise HTTPException(404, "Source path not found")
    return {"file_id": rows[0]["file_id"], "source_relpath": source_relpath}


@router.get("/api/osii/resolve/folder")
def resolve_folder(request: Request, relpath: str):
    row = next(
        (
            r
            for r in library(request).folders()
            if r["path"].strip("/") == relpath.strip("/")
        ),
        None,
    )
    if row is None:
        raise HTTPException(404, "Folder not found")
    return {"folder_id": row["folder_id"], "relpath": relpath}


@router.get("/api/osii/folders/{folder_id}/manifest")
def folder_manifest(request: Request, folder_id: str):
    lib = library(request)
    scope = {"scope_type": "folder", "folder_id": folder_id}
    return {
        "node": {"folder_id": folder_id, "path_hint": lib.scope(scope).identifier},
        "docs": [
            {"file_id": d.file_id, "source_relpath": d.source_relpath}
            for d in lib.documents(scope)
        ],
    }


@router.get("/api/collections/{collection_id}/artifacts")
def collection_artifacts(request: Request, collection_id: str):
    result = library(request).artifact_summary(
        {"scope_type": "collection", "collection_id": collection_id}
    )
    return {
        "collection_id": collection_id,
        "artifacts": result["artifact_summary"],
        "actions": result["actions"],
    }


@router.get("/api/collections/{collection_id}/syntheses")
def collection_syntheses(request: Request, collection_id: str):
    lib = library(request)
    collection = lib.backend.collections.get(collection_id)
    if collection is None:
        raise KeyError("Collection not found")
    scope = {"scope_type": "collection", "collection_id": collection_id}
    return {
        "collection_id": collection_id,
        "collection": lib.collection_view(collection),
        "current_text": lib.synthesis(scope),
        "current_toml": None,
        "syntheses": lib.syntheses(scope),
    }


@router.post("/api/collections/{collection_id}/syntheses")
def collection_synthesis(request: Request, collection_id: str, payload: dict):
    flow = workflow(request)
    job = flow.submit_scope(
        {"scope_type": "collection", "collection_id": collection_id},
        payload["synthesizer_name"],
        "synthesizer",
        payload.get("synthesizer_config"),
        payload.get("expert_context"),
    )
    return {"run_id": job.job_id, "status": job.state, "collection_id": collection_id}


@router.get("/api/osii/folders/{folder_id}/syntheses")
def folder_syntheses(request: Request, folder_id: str):
    return {
        "folder_id": folder_id,
        "syntheses": library(request).syntheses(
            {"scope_type": "folder", "folder_id": folder_id}
        ),
    }


@router.get("/api/catalog/artifacts")
def catalog_artifacts(
    request: Request,
    scope_type: str | None = None,
    scope_id: str | None = None,
    kind: str | None = None,
):
    lib = library(request)
    rows = lib.query(
        "SELECT * FROM scope_products WHERE current_revision IS NOT NULL ORDER BY scope_type,scope_id,filename"
    )
    items = [
        row
        for row in rows
        if (not scope_type or row["scope_type"] == scope_type)
        and (not scope_id or row["scope_id"] == scope_id)
        and (not kind or row["artifact_type"] == kind)
    ]
    return {"items": items, "total": len(items)}


@router.get("/api/chat/health")
def chat_health():
    return {"status": "ok", "service": "osii-core-chat"}


@router.get("/api/embeddings/meta")
def embedding_meta(request: Request):
    rows = library(request).query(
        "SELECT DISTINCT metadata->'embedding_identity' AS identity FROM documents WHERE active AND metadata ? 'embedding_identity'"
    )
    return {"backend": "postgres", "indexes": [row["identity"] for row in rows]}


@router.post("/api/embeddings/build")
def build_embeddings(request: Request, payload: dict):
    lib = library(request)
    from osii.domain.model_provider_config import selected_processor
    from osii.domain.processing.postgres_workflow import configuration_stamp, processor

    flow = workflow(request)
    name = selected_processor("embedder", osii_root=flow.root)
    processor(flow.root, name, "embedder")
    items = [
        {"file_id": d.file_id, "display": d.filename, "status": "done", "steps": {}}
        for d in lib.documents()
    ]
    if not items:
        raise HTTPException(422, "No saved documents to embed")
    options = {
        **payload,
        "build_embeddings": True,
        "embedder_name": name,
        "rebuild_embeddings": True,
    }
    job = flow.queue.submit(
        "local-intake",
        {
            "workflow": "library",
            "options": options,
            "items": items,
            "tool_label": "Full index rebuild",
            "configuration_stamp": configuration_stamp(flow.root),
        },
    )
    lib.set_setting("embedding_build", job.job_id)
    return {
        "job_id": "segments",
        "run_id": job.job_id,
        "status": "running",
        "queue_status": "queued",
    }


@router.get("/api/embeddings/build/{job_id}")
def embedding_status(request: Request, job_id: str):
    lib = library(request)
    row = workflow(request).queue.get(
        lib.setting("embedding_build") if job_id == "segments" else job_id
    )
    if row is None:
        raise HTTPException(404, "Embedding run not found")
    return {
        "run_id": row.job_id,
        "status": row.state,
        "queue_status": row.state,
        "error": row.logs[-1] if row.state == "error" and row.logs else None,
    }


@router.get("/api/chat/profiles")
def chat_profiles(request: Request):
    from osii.rag.local_experiments import profile_catalog

    return profile_catalog(
        library(request).backend.root, request.app.state.rag_reranker
    )


@router.post("/api/chat/compare")
def chat_compare(request: Request, payload: dict):
    from osii.rag.local_experiments import compare_profiles
    from osii.rag.models import CompareRequest

    return compare_profiles(
        library(request).backend.root,
        CompareRequest.model_validate(payload),
        reranker=request.app.state.rag_reranker,
        library=library(request),
    )


def topic_space(request, scope):
    lib = library(request)
    revision, rows = lib.chunks(scope)
    identities = {
        json.dumps(row["metadata"].get("embedding_identity"), sort_keys=True)
        for row in rows
        if row.get("embedding")
    }
    if len(identities) != 1:
        raise HTTPException(409, "Build compatible embeddings for this scope first")
    identity = json.loads(next(iter(identities)))
    if not identity or identity["provider"] == "local.hashing":
        raise HTTPException(
            409, "Topics require semantic embeddings, not lexical hashing vectors"
        )
    docs = [
        {
            **d.metadata,
            "file_id": d.file_id,
            "filename": d.filename,
            "source_relpath": d.source_relpath,
            "media_type": d.media_type,
        }
        for d in lib.documents(scope)
    ]
    return docs, rows, identity["model"], revision


@router.post("/api/topics/map")
def topic_map(request: Request, payload: dict):
    from osii.domain.topics import topic_map

    return topic_map(
        *topic_space(request, payload.get("scope") or {}), limit=payload.get("limit")
    )


@router.post("/api/topics/related")
def related_documents(request: Request, payload: dict):
    from osii.domain.topics import related_documents

    return related_documents(
        *topic_space(request, payload.get("scope") or {}),
        file_id=payload["file_id"],
        limit=max(1, min(50, int(payload.get("limit", 12)))),
    )


@router.get("/api/objects/{file_id}/governance")
def governance(request: Request, file_id: str):
    lib = library(request)
    lib.meta(file_id)
    return {
        "file_id": file_id,
        "governance": lib.setting(
            "governance:" + file_id,
            {
                "sensitivity_labels": [],
                "tags": [],
                "handling_notes": "",
                "updated_utc": None,
            },
        ),
    }


@router.put("/api/objects/{file_id}/governance")
def edit_governance(request: Request, file_id: str, payload: dict):
    from osii.domain.governance import _clean_values
    from datetime import UTC, datetime

    lib = library(request)
    lib.meta(file_id)
    value = {
        "sensitivity_labels": _clean_values(payload.get("sensitivity_labels", [])),
        "tags": _clean_values(payload.get("tags", [])),
        "handling_notes": str(payload.get("handling_notes") or "").strip(),
        "updated_utc": datetime.now(UTC).isoformat(),
    }
    lib.set_setting("governance:" + file_id, value)
    return {"file_id": file_id, "governance": value}


@router.get("/api/objects/{file_id}/keywords/manual")
def manual_keywords(request: Request, file_id: str):
    lib = library(request)
    lib.meta(file_id)
    return {
        "file_id": file_id,
        "keywords": lib.setting("manual_keywords:" + file_id, []),
    }


@router.put("/api/objects/{file_id}/keywords/manual")
def edit_keywords(request: Request, file_id: str, payload: dict):
    from osii.domain.keywords.manual import _clean_keywords

    lib = library(request)
    lib.meta(file_id)
    keywords = _clean_keywords(payload.get("keywords", []))
    lib.set_setting("manual_keywords:" + file_id, keywords)
    return {"file_id": file_id, "keywords": keywords}


@router.get("/api/keyword-sets")
def keyword_sets(request: Request):
    return {"keyword_sets": library(request).setting("keyword_sets", [])}


@router.post("/api/keyword-sets")
def create_keyword_set(request: Request, payload: dict):
    from osii.domain.keywords.manual import _clean_keywords
    import uuid

    lib = library(request)
    name = str(payload.get("name", "")).strip()
    keywords = _clean_keywords(payload.get("keywords", []))
    if not name or len(name) > 120 or not keywords:
        raise ValueError("Provide a name and at least one keyword")
    with lib.engine.begin() as conn:
        lib.sql(conn, "SELECT pg_advisory_xact_lock(914036)")
        row = (
            lib.sql(
                conn, "SELECT value FROM settings WHERE id='keyword_sets' FOR UPDATE"
            ).scalar()
            or []
        )
        if any(r["name"].casefold() == name.casefold() for r in row):
            raise ValueError("Keyword set name already exists")
        record = {
            "id": "keywords-" + uuid.uuid4().hex[:12],
            "name": name,
            "keywords": keywords,
        }
        row.append(record)
        lib.sql(
            conn,
            "INSERT INTO settings VALUES ('keyword_sets',CAST(:value AS jsonb)) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
            value=json.dumps(row),
        )
    return {"keyword_set": record}


@router.delete("/api/keyword-sets/{set_id}")
def remove_keyword_set(request: Request, set_id: str):
    lib = library(request)
    with lib.engine.begin() as conn:
        lib.sql(conn, "SELECT pg_advisory_xact_lock(914036)")
        row = (
            lib.sql(
                conn, "SELECT value FROM settings WHERE id='keyword_sets' FOR UPDATE"
            ).scalar()
            or []
        )
        retained = [r for r in row if r["id"] != set_id]
        if len(retained) == len(row):
            raise KeyError("Keyword set not found")
        lib.sql(
            conn,
            "UPDATE settings SET value=CAST(:value AS jsonb) WHERE id='keyword_sets'",
            value=json.dumps(retained),
        )
    return {"ok": True}


@router.get("/api/objects/{file_id}/metadata")
def document_metadata(request: Request, file_id: str):
    lib = library(request)
    lib.meta(file_id)
    payload = {
        "scope": {"scope_type": "object", "file_id": file_id},
        "filename": "document_metadata--manual.json",
    }
    try:
        history = lib.history(payload)
        return {
            "file_id": file_id,
            "revision": history["current"],
            "document_metadata": history["data"].get("document_metadata"),
        }
    except KeyError:
        return {
            "file_id": file_id,
            "revision": None,
            "document_metadata": lib.reader.get_document(file_id).metadata.get(
                "document_metadata"
            )
            or None,
        }


@router.put("/api/objects/{file_id}/metadata")
def edit_document_metadata(request: Request, file_id: str, payload: dict):
    from osii.domain.document_metadata import METADATA_FIELDS
    from osii.processor_sdk import DocumentMetadata

    lib = library(request)
    lib.meta(file_id)
    if "expected_revision" not in payload:
        raise ValueError("expected_revision is required")
    values = payload.get("values")
    if not isinstance(values, dict) or set(values) - set(METADATA_FIELDS):
        raise ValueError("Provide document metadata fields only")
    metadata = DocumentMetadata.model_validate(
        {
            "method": "human",
            "model": None,
            **{name: {"value": values.get(name)} for name in METADATA_FIELDS},
        }
    ).model_dump(mode="json")
    data = {
        "artifact_type": "document_metadata",
        "title": "Document metadata",
        "document_metadata": metadata,
    }
    ref = ProductRef(ReadScope("object", file_id), "document_metadata--manual.json")
    if payload["expected_revision"] is None:
        lib.create_manual_product(ref, data)
    else:
        lib.backend.products.save(
            ref, data, expected_revision=payload["expected_revision"], activate=True
        )
    return document_metadata(request, file_id)


@router.delete("/api/enrichments/payload")
def remove_enrichment(request: Request, payload: dict):
    lib = library(request)
    ref = lib.product_ref(payload)
    with lib.engine.begin() as conn:
        row = lib.backend.products._product(conn, ref, lock=True)
        # Preserve revisions when hiding a product, just as the sidecar history.
        lib.sql(
            conn,
            "UPDATE scope_products SET current_revision=NULL WHERE id=:id",
            id=row["id"],
        )
    return {"deleted": True, "filename": ref.filename, "scope": payload["scope"]}


@router.post("/api/objects/{file_id}/extractions/{variant_id}/primary")
def promote_extraction(request: Request, file_id: str, variant_id: str):
    from osii.domain.processing.postgres_workflow import chunk_rows

    lib = library(request)
    record = lib.reader.get_representation(file_id, variant_id)
    if record is None:
        raise KeyError("Extraction not found")
    spans = [
        {
            "id": s.segment_id,
            "char_start": s.char_start,
            "char_end": s.char_end,
            "source_origin": s.source_origin,
        }
        for s in record.segments
    ]
    with lib.engine.begin() as conn:
        row = (
            lib.sql(
                conn,
                "SELECT metadata FROM documents WHERE file_id=:id FOR UPDATE",
                id=file_id,
            )
            .mappings()
            .one()
        )
        metadata = dict(row["metadata"])
        edited = metadata.pop("edited_representation", None)
        if edited and not any(
            r.get("id") == edited["revision"]
            for r in metadata.get("edited_text_history", [])
        ):
            metadata.setdefault("edited_text_history", []).append(
                {
                    **edited,
                    "id": edited["revision"],
                    "origin": "human",
                    "retired_by_extraction": record.representation_id,
                }
            )
        metadata.update(
            primary_extraction_id=record.representation_id,
            segments=spans,
            stale={"embeddings": True, "search_chunks": False},
        )
        response = lib.sql(
            conn,
            "SELECT response FROM extractions WHERE id=:id AND file_id=:file",
            id=record.representation_id,
            file=file_id,
        ).scalar()
        if response:
            metadata["extractor"] = response.get("processor", {})
        lib.sql(
            conn,
            "UPDATE documents SET text=:text,metadata=CAST(:meta AS jsonb),updated_at=CURRENT_TIMESTAMP WHERE file_id=:id",
            id=file_id,
            text=record.text,
            meta=json.dumps(metadata),
        )
        lib.sql(conn, "DELETE FROM chunks WHERE file_id=:id", id=file_id)
        if response:
            lib.sql(
                conn,
                "DELETE FROM artifacts WHERE file_id=:id AND kind NOT IN('synthesis','enrichment','manual_metadata','manual_metadata_history')",
                id=file_id,
            )
            for artifact in response.get("artifacts", []):
                identity = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        record.representation_id + ":" + artifact["id"],
                    )
                )
                lib.sql(
                    conn,
                    "INSERT INTO artifacts VALUES(:id,:file,:kind,CAST(:payload AS jsonb))",
                    id=identity,
                    file=file_id,
                    kind=artifact["kind"],
                    payload=json.dumps(artifact),
                )
        for chunk in chunk_rows(file_id, record.text, spans):
            lib.sql(
                conn,
                "INSERT INTO chunks(chunk_id,file_id,text,char_start,char_end,source_origin) VALUES (:chunk_id,:file_id,:text,:char_start,:char_end,CAST(:source_origin AS jsonb))",
                **{**chunk, "source_origin": json.dumps(chunk["source_origin"])},
            )
        lib.sql(conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'")
    return extractions(request, file_id)


@router.post("/api/objects/{file_id}/extractions/{variant_id}/editable-copy")
def extraction_copy(request: Request, file_id: str, variant_id: str, payload: dict):
    lib = library(request)
    scope = {"scope_type": "object", "file_id": file_id}
    if payload.get("artifact_id"):
        artifacts = extraction_artifacts(request, file_id, variant_id)["artifacts"]
        artifact = next(
            (row for row in artifacts if row["id"] == payload["artifact_id"]), None
        )
        if artifact is None or not isinstance(artifact["data"], dict):
            raise ValueError("Choose an artifact with a JSON preview")
        data = artifact["data"]
    else:
        record = lib.reader.get_representation(file_id, variant_id)
        if record is None:
            raise KeyError("Extraction not found")
        data = {
            "artifact_type": "text",
            "title": "Corrected extraction",
            "text": record.text,
        }
    name = (
        "extraction-copy--"
        + hashlib.sha256(
            f"{variant_id}:{payload.get('artifact_id')}".encode()
        ).hexdigest()[:20]
        + ".json"
    )
    ref = ProductRef(ReadScope("object", file_id), name)
    try:
        lib.backend.products.history(ref)
    except KeyError:
        lib.create_manual_product(ref, data)
    return {"scope": scope, "filename": name, "family": "enrichment"}


@router.get("/api/collections/{collection_id}/export")
def export_collection(request: Request, collection_id: str):
    from osii.domain.storage.postgres_packages import export_collection

    return Response(
        export_collection(library(request), collection_id),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="osii-collection.zip"'},
    )


@router.post("/api/packages/import")
async def import_collection(request: Request, package: UploadFile = File(...)):
    from osii.domain.storage.postgres_packages import (
        import_collection,
        MAX_ARCHIVE_BYTES,
    )
    from starlette.concurrency import run_in_threadpool

    try:
        content = await package.read(MAX_ARCHIVE_BYTES + 1)
    finally:
        await package.close()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise HTTPException(413, "Package exceeds the 512 MB safety limit")
    return await run_in_threadpool(import_collection, library(request), content)


@router.post("/api/runs/recover")
def recover_runs(request: Request):
    lib = library(request)
    with lib.engine.begin() as conn:
        rows = (
            lib.sql(
                conn,
                """UPDATE jobs SET status=CASE status WHEN 'pausing' THEN 'paused'
            WHEN 'cancelling' THEN 'cancelled' ELSE 'queued' END,worker_id=NULL,lease_until=NULL
            WHERE status IN('running','pausing','cancelling') AND lease_until<CURRENT_TIMESTAMP RETURNING id""",
            )
            .scalars()
            .all()
        )
    return {
        "recovered_run_ids": rows,
        "recovered_count": len(rows),
        "worker": runs(request)["worker"],
    }


@router.post("/api/intake/rescan-sources")
def rescan_sources(request: Request, payload: dict):
    from osii.domain.processing.intake import expand_queue_to_files
    from osii.domain.processing.pathing import source_relpath
    from osii.domain.storage.ids import compute_file_id

    lib = library(request)
    shared = request.app.state.shared_volume_root.resolve()
    selected, _ = expand_queue_to_files(
        queue_items=[
            {
                "path": str(shared),
                "kind": "folder",
                "source": "shared",
                "display": shared.name,
            }
        ],
        include_subfolders=True,
        include_patterns=[],
        exclude_patterns=[],
        show_hidden=bool(payload.get("show_hidden", False)),
        max_files=None,
        max_total_size=None,
        shared_root=shared,
        upload_root=request.app.state.upload_originals_root,
    )
    by_hash = {}
    for path in selected:
        by_hash.setdefault(compute_file_id(path), []).append(path)
    moved = []
    missing = []
    unchanged = []
    ambiguous = []
    for doc in lib.documents():
        matches = by_hash.get(doc.file_id, [])
        current = [
            p for p in matches if source_relpath(p, shared.parent) == doc.source_relpath
        ]
        if current:
            unchanged.append(
                {"file_id": doc.file_id, "source_relpath": doc.source_relpath}
            )
        elif len(matches) == 1:
            moved.append(
                {
                    "file_id": doc.file_id,
                    "old_source_relpath": doc.source_relpath,
                    "new_source_relpath": source_relpath(matches[0], shared.parent),
                    "source_path": str(matches[0]),
                }
            )
        elif not matches:
            missing.append(
                {"file_id": doc.file_id, "source_relpath": doc.source_relpath}
            )
        else:
            ambiguous.append(
                {"file_id": doc.file_id, "matches": [str(p) for p in matches]}
            )
    result = {
        "moved": moved,
        "missing_source": missing,
        "unchanged": unchanged,
        "ambiguous": ambiguous,
        "changed": [],
        "new_files": [],
        "summary": {
            "moved": len(moved),
            "missing_source": len(missing),
            "unchanged": len(unchanged),
            "ambiguous": len(ambiguous),
        },
    }
    if payload.get("apply"):
        with lib.engine.begin() as conn:
            for row in moved:
                record = (
                    lib.sql(
                        conn,
                        "SELECT metadata,source_relpath FROM documents WHERE file_id=:id FOR UPDATE",
                        id=row["file_id"],
                    )
                    .mappings()
                    .one()
                )
                if record["source_relpath"] != row["old_source_relpath"]:
                    raise AuthoringConflict(
                        "Paths changed during rescan; retry without applying"
                    )
                metadata = {
                    **record["metadata"],
                    "source_absolute_path": row["source_path"],
                }
                lib.sql(
                    conn,
                    "UPDATE documents SET source_relpath=:path,filename=:name,metadata=CAST(:meta AS jsonb),updated_at=CURRENT_TIMESTAMP WHERE file_id=:id",
                    id=row["file_id"],
                    path=row["new_source_relpath"],
                    name=Path(row["source_path"]).name,
                    meta=json.dumps(metadata),
                )
            lib.sql(conn, "UPDATE datasets SET revision=revision+1 WHERE id='shared'")
        result["applied"] = {
            "moved_updated": len(moved),
            "missing_marked": 0,
            "changed_marked": 0,
            "active_marked": len(unchanged) + len(moved),
            "folder_tree_rebuilt": True,
        }
    return result


@router.get("/api/osii/root")
def root_descriptor(request: Request):
    return library(request).setting(
        "sidecar:root.toml",
        {"collection": {"name": "Library"}, "storage_backend": "postgres"},
    )


@router.get("/api/osii/root/overview")
def root_overview(request: Request):
    return library(request).overview({"scope_type": "root"})


@router.get("/api/osii/root/synth")
def root_synthesis(request: Request):
    return {"synth": library(request).synthesis({"scope_type": "root"})}


@router.get("/api/osii/folders/{folder_id}/overview")
def folder_overview(request: Request, folder_id: str):
    return library(request).overview({"scope_type": "folder", "folder_id": folder_id})


@router.get("/api/osii/folders/{folder_id}/synth")
def folder_synth(request: Request, folder_id: str):
    return {
        "folder_id": folder_id,
        "synth": library(request).synthesis(
            {"scope_type": "folder", "folder_id": folder_id}
        ),
    }


@router.get("/api/osii/folders/{folder_id}/synth-toml")
def folder_synth_metadata(request: Request, folder_id: str):
    rows = library(request).product_rows(
        {"scope_type": "folder", "folder_id": folder_id}, "synthesis"
    )
    return rows[-1]["provenance"] if rows else {}


@router.get("/api/osii/docs/{file_id}/meta")
def doc_meta(request: Request, file_id: str):
    return library(request).meta(file_id)


@router.get("/api/osii/docs/{file_id}/overview")
def doc_overview(request: Request, file_id: str):
    return document(request, file_id)["overview"]


@router.get("/api/osii/docs/{file_id}/manifest")
def doc_manifest(request: Request, file_id: str):
    return manifest(request, file_id)


@router.get("/api/osii/docs/{file_id}/texts")
def doc_texts(request: Request, file_id: str):
    return {
        "file_id": file_id,
        "texts": [r for r in library(request).manifest(file_id) if r["kind"] == "text"],
    }


@router.get("/api/osii/docs/{file_id}/texts/{seg}")
def doc_text(request: Request, file_id: str, seg: int):
    record = library(request).reader.get_representation(file_id, "canonical")
    segment = (
        next((s for s in record.segments if s.segment_id == f"seg-{seg:06d}"), None)
        if record
        else None
    )
    if segment is None:
        raise KeyError("Text segment not found")
    return {
        "file_id": file_id,
        "record": next(
            r
            for r in library(request).manifest(file_id)
            if r["id"] == segment.segment_id
        ),
        "text": segment.text,
    }


@router.get("/api/osii/docs/{file_id}/images")
def doc_images(request: Request, file_id: str):
    return {"file_id": file_id, "images": library(request).images(file_id)}


@router.get("/api/osii/docs/{file_id}/images/{artifact_id}")
def doc_image(request: Request, file_id: str, artifact_id: str):
    row = next(
        (r for r in library(request).images(file_id) if r["id"] == artifact_id), None
    )
    if row is None:
        raise KeyError("Image artifact not found")
    return {"file_id": file_id, "record": row, "path": row["path"]}


@router.get("/api/osii/docs/{file_id}/syntheses")
def doc_syntheses(request: Request, file_id: str):
    return {"file_id": file_id, "syntheses": syntheses(request, file_id)["syntheses"]}


@router.get("/api/osii/docs/{file_id}/synth")
def doc_synth(request: Request, file_id: str):
    return {
        "file_id": file_id,
        "synth": library(request).synthesis(
            {"scope_type": "object", "file_id": file_id}
        ),
    }


@router.get("/api/osii/docs/{file_id}/synth-toml")
def doc_synth_metadata(request: Request, file_id: str):
    rows = library(request).product_rows(
        {"scope_type": "object", "file_id": file_id}, "synthesis"
    )
    return rows[-1]["provenance"] if rows else {}


@router.get("/api/osii/stats")
def osii_stats(request: Request):
    lib = library(request)
    return {
        "backend": "postgres",
        "documents": lib.query("SELECT count(*) AS count FROM documents WHERE active")[
            0
        ]["count"],
        "artifacts": lib.query("SELECT count(*) AS count FROM artifacts")[0]["count"],
    }


def deletion_source(request, file_id, mode):
    try:
        return source_file(request, file_id)
    except HTTPException as exc:
        if exc.status_code == 404 or mode == "sidecar_only":
            return None
        raise


@router.post("/api/objects/{file_id}/deletion-preview")
def deletion_preview(request: Request, file_id: str, payload: dict):
    mode = payload.get("mode", "sidecar_only")
    return library(request).deletion_preview(
        file_id, mode, deletion_source(request, file_id, mode)
    )


@router.delete("/api/objects/{file_id}")
def delete_document(request: Request, file_id: str, payload: dict):
    mode = payload.get("mode", "")
    try:
        return library(request).delete_document(
            file_id,
            mode,
            payload.get("preview_token", ""),
            payload.get("confirmation", ""),
            deletion_source(request, file_id, mode),
        )
    except (RuntimeError, OSError) as exc:
        raise HTTPException(409, str(exc)) from None
