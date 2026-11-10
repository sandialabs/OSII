"""Hosted scope-tool orchestration over bounded PostgreSQL evidence snapshots."""

from __future__ import annotations
import hashlib
from sqlalchemy import select, func
from osii.persistence.postgres import documents, identifier, now
from osii.persistence.scope_products import ScopeProducts, address
from osii.domain.library import scope_documents
from osii.server.intake import configuration_stamp
from osii.server.processors import catalog, bounded_config, invoke
from osii.processor_sdk import (
    DocumentInput,
    ScopeInput,
    SynthesisRequest,
    EnrichmentRequest,
    WikiMarkdownArtifactData,
)

MAX_DOCUMENTS = 1000
MAX_CHARACTERS = 180000


def scoped_headers(store, scope, actor_id):
    address(scope)
    return scope_documents(
        store.catalog_documents(), scope, store.collection_records(actor_id)
    )


def tool_catalog(store, settings, actor):
    methods = []
    config = store.configuration()
    for row in catalog(store, settings):
        descriptor = row.get("descriptor")
        if not descriptor:
            continue
        capabilities = descriptor.get("capabilities", {})
        outputs = capabilities.get("output_kinds", [])
        scoped = row["kind"] in {"synthesizer", "enricher"}
        action = (
            "wiki.write"
            if "wiki_markdown" in outputs
            else "metadata.suggest"
            if "document_metadata" in outputs
            else "analyze"
        )
        if not scoped:
            action = {"extractor": "text.read", "embedder": "embedding.build"}.get(
                row["kind"], "analyze"
            )
        methods.append(
            {
                "id": row["id"],
                "label": row["display_name"],
                "version": descriptor["version"],
                "action": action,
                "execution": "scope" if scoped else "intake",
                "scopes": capabilities.get("scope_types", []),
                "inputs": ["text"] if scoped else ["source"],
                "outputs": outputs,
                "config_schema": descriptor.get("config_schema", {}),
                "model_requirements": row.get("model_requirements", {}),
                "bindings": {"chat": "server.chat"} if config.get("chat_model") else {},
                "configuration_error": row.get("detail")
                if not row["available"]
                else None,
                "limits": {"documents": MAX_DOCUMENTS, "characters": MAX_CHARACTERS},
                "resume": "frozen-inputs" if scoped else "per-document",
            }
        )
    models = (
        [
            {
                "id": "server.chat",
                "label": config.get("chat_model_name") or config["chat_model"],
                "capabilities": ["chat"],
            }
        ]
        if config.get("chat_model")
        else []
    )
    return {
        "library_id": hashlib.sha256(("hosted:" + actor["id"]).encode()).hexdigest()[
            :20
        ],
        "methods": methods,
        "models": models,
        "defaults": {"chat": "server.chat"} if models else {},
        "permissions": {
            "run": actor["role"] == "admin",
            "edit": actor["role"] in {"admin", "curator"},
        },
    }


def snapshot(store, scope, actor_id):
    headers = sorted(
        scoped_headers(store, scope, actor_id), key=lambda row: row["file_id"]
    )
    if not headers:
        raise ValueError("No documents are in this scope")
    if len(headers) > MAX_DOCUMENTS:
        raise ValueError(
            f"This tool accepts at most {MAX_DOCUMENTS} documents; choose a folder or collection"
        )
    # Reserve room for source identifiers and processor instructions as well as text.
    overhead = sum(len(row["file_id"]) + len(row["filename"]) + 64 for row in headers)
    budget = MAX_CHARACTERS - overhead
    if budget < len(headers):
        raise ValueError(
            "Source labels exceed the tool input budget; choose a smaller scope"
        )
    allowance = budget // len(headers)
    ids = [row["file_id"] for row in headers]
    with store.engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as c:
        rows = (
            c.execute(
                select(
                    documents.c.file_id,
                    documents.c.filename,
                    documents.c.media_type,
                    documents.c.source_relpath,
                    documents.c.metadata["primary_extraction_id"].astext.label(
                        "extraction_id"
                    ),
                    func.length(documents.c.text).label("full_chars"),
                    func.md5(documents.c.text).label("text_fingerprint"),
                    func.substr(documents.c.text, 1, allowance).label("text"),
                )
                .where(documents.c.active, documents.c.file_id.in_(ids))
                .order_by(documents.c.file_id)
            )
            .mappings()
            .all()
        )
    texts = [
        {
            **dict(row),
            "truncated": row["full_chars"] > len(row["text"]),
            "retained_spans": [{"start": 0, "end": len(row["text"])}],
        }
        for row in rows
        if row["text"].strip()
    ]
    if not texts:
        raise ValueError("Read document text before running a library tool")
    return {
        "member_ids": ids,
        "documents": texts,
        "text_chars": sum(len(row["text"]) for row in texts),
        "truncated_documents": sum(row["truncated"] for row in texts),
        "documents_without_text": len(ids) - len(texts),
    }


def submit(store, settings, actor, payload):
    scope = payload["scope"]
    kind, _ = address(scope)
    rows = catalog(store, settings)
    choice = next(
        (
            row
            for row in rows
            if row.get("id") == payload["enricher_name"]
            and row.get("kind") in {"synthesizer", "enricher"}
        ),
        None,
    )
    if choice is None or not choice.get("available"):
        raise ValueError("The selected scope tool is unavailable; check Setup")
    if kind not in choice["descriptor"]["capabilities"]["scope_types"]:
        raise ValueError("This method does not support the selected scope")
    bindings = payload.get("model_bindings") or {}
    if set(bindings) - {"chat"} or any(
        value not in {"", "server.chat"} for value in bindings.values()
    ):
        raise ValueError("Choose the configured hosted writing model")
    frozen = snapshot(store, scope, actor["id"])
    config = bounded_config(payload.get("enricher_config") or {}, choice)
    title = (
        scope.get("collection_id") or scope.get("folder_id") or "Library"
        if kind != "object"
        else next(row["filename"] for row in frozen["documents"])
    )
    body = {
        "workflow": "tool",
        "actor_id": actor["id"],
        "scope": scope,
        "selection": choice,
        "config": config,
        "frozen": frozen,
        "configuration_stamp": configuration_stamp(store, settings),
        "expert_context": payload.get("expert_context") or "",
        "product_parents": ScopeProducts(store).parents(scope, choice["id"]),
        "tool_id": choice["id"],
        "tool_label": choice["display_name"],
        "scope_title": str(title),
        "items": [{"display": choice["display_name"], "status": "pending"}],
    }
    jid = store.enqueue("tool", body)
    store.record("scope_tool_queued", actor["id"], jid)
    return {
        "run_id": jid,
        "status": "queued",
        "scope": scope,
        "enricher_name": choice["id"],
        "input_summary": {k: v for k, v in frozen.items() if k != "documents"},
    }


def input_state(store, scope, provenance, actor_id):
    try:
        current = scoped_headers(store, scope, actor_id)
        if sorted(row["file_id"] for row in current) != sorted(
            provenance.get("member_ids", [])
        ):
            return "stale"
        ids = [row["file_id"] for row in current]
        with store.engine.connect() as c:
            fingerprints = {
                row.file_id: (row.extraction_id, row.fingerprint)
                for row in c.execute(
                    select(
                        documents.c.file_id,
                        documents.c.metadata["primary_extraction_id"].astext.label(
                            "extraction_id"
                        ),
                        func.md5(documents.c.text).label("fingerprint"),
                    ).where(documents.c.file_id.in_(ids), documents.c.active)
                )
            }
        if any(
            fingerprints.get(row["file_id"])
            != (row.get("extraction_id"), row.get("text_fingerprint"))
            for row in provenance.get("inputs", [])
        ):
            return "stale"
        return "current"
    except (KeyError, ValueError):
        return "stale"


def execute(store, settings, provider, job, worker, stopping, report):
    payload = job["payload"]
    actor = store.account(user_id=payload["actor_id"])
    if not actor or not actor["active"] or actor["role"] != "admin":
        raise ValueError(
            "The account that queued this tool no longer has processing permission"
        )
    scoped_headers(store, payload["scope"], actor["id"])
    if configuration_stamp(store, settings) != payload["configuration_stamp"]:
        raise ValueError("Model or processor settings changed; start a new tool run")
    if stopping.is_set():
        return True
    if store.checkpoint(job["id"], worker) != "running":
        return False
    item = payload["items"][0]
    if item["status"] == "done":
        return False
    choice = payload["selection"]
    frozen = payload["frozen"]
    kind, identity = address(payload["scope"])
    scope = ScopeInput(
        scope_type=kind,
        scope_id=identity,
        documents=[
            DocumentInput(
                file_id=row["file_id"],
                filename=row["filename"],
                media_type=row["media_type"],
                text=row["text"],
                metadata={
                    "source_relpath": row["source_relpath"],
                    "extraction_id": row["extraction_id"],
                    "truncated": row["truncated"],
                },
            )
            for row in frozen["documents"]
        ],
        metadata={"coverage": {k: v for k, v in frozen.items() if k != "documents"}},
    )
    request_class = (
        SynthesisRequest if choice["kind"] == "synthesizer" else EnrichmentRequest
    )
    request = request_class(
        request_id=identifier(),
        scope=scope,
        config=payload["config"],
        expert_context=payload["expert_context"] or None,
    )
    report("Running " + choice["display_name"] + " on saved scope inputs.")

    def checkpoint(key, value=None):
        calls = item.setdefault("synthesis_calls", {})
        if value is None:
            return calls.get(key)
        calls[key] = value
        store.update_processing_item(job["id"], worker, 0, item)

    response = invoke(
        store,
        settings,
        provider,
        choice,
        request,
        job_id=job["id"],
        worker=worker,
        checkpoint=checkpoint,
    )
    response = response.model_validate_json(
        response.model_dump_json().replace("\\u0000", "\\ufffd")
    )
    outputs = []
    if choice["kind"] == "synthesizer":
        wiki = WikiMarkdownArtifactData(
            title=payload["scope_title"] + " · " + choice["display_name"],
            markdown=response.markdown,
            citations=response.citations,
        )
        outputs.append(
            {"id": "wiki", "family": "synthesis", "data": wiki.model_dump(mode="json")}
        )
    else:
        for artifact in response.artifacts:
            data = (
                artifact.standard_data.model_dump(mode="json")
                if artifact.standard_data
                else {
                    "artifact_type": "text",
                    "title": artifact.id,
                    "text": artifact.text,
                }
                if artifact.text is not None
                else {
                    "artifact_type": "json",
                    "title": artifact.id,
                    "data": artifact.json_data,
                }
            )
            outputs.append({"id": artifact.id, "family": "enrichment", "data": data})
    if not outputs:
        raise ValueError("The tool returned no usable products")
    actor = store.account(user_id=payload["actor_id"])
    if not actor or not actor["active"] or actor["role"] != "admin":
        raise ValueError("Processing permission was revoked during this run")
    # Visibility may have changed while the processor request was in flight.
    scoped_headers(store, payload["scope"], actor["id"])
    provenance = {
        "run_id": job["id"],
        "tool": choice["id"],
        "version": choice["descriptor"]["version"],
        "config": payload["config"],
        "expert_context": payload["expert_context"],
        "writing_model": store.configuration().get("chat_model")
        if choice.get("model_requirements", {}).get("chat")
        else None,
        "configuration_stamp": payload["configuration_stamp"],
        "scope": payload["scope"],
        "member_ids": frozen["member_ids"],
        "inputs": [
            {k: v for k, v in row.items() if k != "text"} for row in frozen["documents"]
        ],
        "input_summary": {
            k: v for k, v in frozen.items() if k not in {"documents", "member_ids"}
        },
    }
    ScopeProducts(store).generated(
        payload["scope"], choice["id"], outputs, job, worker, provenance
    )
    item.update(status="done", finished_at=now().isoformat())
    report(
        "Scope products and provenance saved. Originals and extracted text are unchanged."
    )
    store.checkpoint(job["id"], worker, item=item, index=0)
    return False
