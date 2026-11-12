"""Standalone processing orchestration with PostgreSQL-owned jobs and results.

Uses the existing Processor API, chunking, and whole-scope batching algorithms.
It neither imports hosted authentication nor writes canonical sidecar products.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import threading
import time
import uuid
import sys

from osii.domain.read.contracts import ReadScope
from osii.domain.storage.commits import (
    ProcessingCommit,
    ScopeProcessingCommit,
    SourceRecord,
    InputRevision,
    ScopeInputRevision,
    JobCheckpoint,
    extraction_material,
    text_digest,
)
from osii.domain.storage.job_store import JobOwnershipLost
from osii.processor_sdk import (
    ProcessorClient,
    ProcessorDescriptor,
    ExtractionRequest,
    DocumentInput,
    ScopeInput,
    SynthesisRequest,
    EnrichmentRequest,
    EmbeddingRequest,
    EmbeddingInput,
    ModelContext,
)
from osii.indexing.chunking import chunk_saved_text as chunk_rows
from osii.domain.storage.objects import iso_mtime_utc, iso_birthtime_utc


def now():
    return datetime.now(UTC).isoformat()


def configuration_stamp(root):
    from osii.configuration import load_models_config, load_tools_config

    return text_digest(
        json.dumps(
            {"models": load_models_config(root), "tools": load_tools_config(root)},
            sort_keys=True,
        )
    )


def embedding_binding(root, descriptor, endpoint):
    """Credential-free identity of the selected endpoint and model bindings."""
    from osii.configuration import (
        load_models_config,
        model_connection,
        resolve_tool_models,
    )

    bindings = resolve_tool_models(descriptor.name, descriptor.model_requirements, root)
    if descriptor.name in {"ollama.embedder", "openai.embedder"}:
        alias = load_models_config(root).get("defaults", {}).get("embedding")
        if alias:
            bindings = {**bindings, "embedding": alias}
    connections = {}
    for capability, alias in bindings.items():
        value = model_connection(alias, root) or {}
        connections[capability] = {
            key: value.get(key) for key in ("type", "base_url", "model")
        }
    return text_digest(
        json.dumps(
            {
                "processor": {"name": descriptor.name, "version": descriptor.version},
                "endpoint": endpoint.rstrip("/"),
                "connections": connections,
            },
            sort_keys=True,
        )
    )


def processor(root, name, kind):
    from osii.processors.remote import resolve_remote_processor, _commit_descriptor

    # The three model-free Core enrichers already support frozen inputs and an
    # output capture sink. Reuse that boundary, never a temporary sidecar store.
    if kind == "enricher" and name in {
        "stats_keywords",
        "noun_adjective_ngrams",
        "entity_candidates",
    }:
        from osii.enrichment.stats_keywords import StatsKeywordsEnricher
        from osii.enrichment.linguistic_examples import (
            NounAdjectiveNgramEnricher,
            EntityCandidateEnricher,
        )

        implementations = {
            item.name: item
            for item in (
                StatsKeywordsEnricher(),
                NounAdjectiveNgramEnricher(),
                EntityCandidateEnricher(),
            )
        }
        implementation = implementations[name]
        descriptor = ProcessorDescriptor(**implementation.describe(), kind="enricher")

        class Client:
            def enrich(self, request):
                from osii.enrichment.common import frozen_scope_inputs
                from osii.domain.artifacts.enrichment_artifacts import (
                    capture_batch_outputs,
                )

                key = {
                    "object": "file_id",
                    "folder": "folder_id",
                    "collection": "collection_id",
                }.get(request.scope.scope_type)
                scope = {
                    "scope_type": request.scope.scope_type,
                    **({key: request.scope.scope_id} if key else {}),
                }
                documents = [
                    {
                        "file_id": row.file_id,
                        "text": row.text,
                        "representation": "preferred",
                    }
                    for row in request.scope.documents
                ]
                with (
                    frozen_scope_inputs(root, scope, documents),
                    capture_batch_outputs() as outputs,
                ):
                    implementation.enrich(
                        osii_store=root,
                        scope=scope,
                        enricher_config={
                            **request.config,
                            **(
                                {"top_k": 100000, "min_count": 1}
                                if name == "stats_keywords"
                                else {}
                            ),
                        },
                        expert_context=request.expert_context,
                    )
                return {
                    "artifacts": [
                        {"id": item["id"], "data": item["data"]} for item in outputs
                    ]
                }

        return descriptor, Client()
    if kind == "extractor" and name == "tika_catchall":
        name = "tika"
    if name == "native_text" and kind == "extractor":
        name = "local.native-text"
    if name in {"firstN", "collection_firstn"} and kind == "synthesizer":
        name = "local.extractive-preview"
    record = resolve_remote_processor(name, kind)
    return _commit_descriptor(record), ProcessorClient(record["base_url"])


@contextmanager
def model_request(root, descriptor, request_id, bindings=None):
    from osii.processors.remote import _model_context, _revoke_model_context
    from osii.domain.tool_actions import _BINDINGS

    token = (
        _BINDINGS.set((descriptor.name, bindings, None))
        if bindings is not None
        else None
    )
    context = None
    try:
        context = _model_context(
            processor_name=descriptor.name,
            descriptor=descriptor.model_dump(mode="json"),
            request_id=request_id,
            osii_root=root,
        )
        yield context
    finally:
        _revoke_model_context(context)
        if token is not None:
            _BINDINGS.reset(token)


class PostgresWorkflow:
    def __init__(self, library):
        self.library, self.backend = library, library.backend
        self.queue, self.root = self.backend.jobs, self.backend.root
        self.task_index = None

    def run_view(self, job):
        payload = job.payload
        items = payload.get("items", [])
        return {
            **{
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "source_documents",
                    "source_inputs",
                    "staging",
                    "tasks",
                    "batches",
                    "_osii_claim_generation",
                    "configuration_stamp",
                    "budget_started_at",
                }
            },
            "id": job.job_id,
            "queue_job_id": job.job_id,
            "status": job.state,
            "control_state": job.state,
            "logs": list(job.logs),
            "created_at": job.native["created_at"].isoformat(),
            # Resumable vector batches are operational state, not dashboard
            # data. Never serialize vectors or model request context here.
            "items": [
                {k: v for k, v in item.items() if k != "embedding_checkpoint"}
                for item in items
            ],
            "completed": sum(row.get("status") == "done" for row in items),
            "total": len(items),
        }

    def submit_files(
        self, paths, options, *, shared_root, upload_root, staging=None, job_id=None
    ):
        if not paths:
            raise ValueError("Choose at least one file to process")
        paths = list(
            dict.fromkeys(
                str(Path(path) if staging else Path(path).resolve()) for path in paths
            )
        )
        if len(paths) > 10000:
            raise ValueError("Choose at most 10,000 files per run")
        from osii.domain.processing.pathing import source_relpath

        items = []
        for path in paths:
            source = Path(path)
            if staging is None and not source.is_file():
                raise ValueError("A selected source file is unavailable")
            if staging:
                try:
                    relative = source.relative_to(shared_root.parent).as_posix()
                except ValueError:
                    relative = "external/" + source.as_posix().replace(":", "").lstrip(
                        "/"
                    )
            else:
                relative = source_relpath(source, shared_root.parent)
            items.append(
                {
                    "path": path,
                    "display": source.name,
                    "status": "pending",
                    "steps": {},
                    "source_relpath": relative,
                    "error": None,
                }
            )
        allowed = {
            "workflow",
            "run_extraction",
            "extract_mode",
            "extraction_policy",
            "extractor_overrides",
            "extractor_config",
            "synthesizer_name",
            "synthesizer_config",
            "enricher_name",
            "enricher_config",
            "build_embeddings",
            "embedder_name",
            "embedding_model",
            "chunking_method",
            "chunk_size",
            "chunk_overlap",
            "context",
            "collection_id",
            "expected_file_ids",
            "rebuild_embeddings",
        }
        options = {key: value for key, value in options.items() if key in allowed}
        if options.get("build_embeddings"):
            from osii.domain.model_provider_config import selected_processor

            name = options.get("embedder_name") or selected_processor(
                "embedder", osii_root=self.root
            )
            processor(
                self.root, name, "embedder"
            )  # Fail before queueing an unavailable capability.
            options["embedder_name"] = name
        payload = {
            "workflow": options.get("workflow", "intake"),
            "options": options,
            "items": items,
            "configuration_stamp": configuration_stamp(self.root),
            "staging": staging,
        }
        if job_id is None:
            return self.queue.submit("local-intake", payload)
        with self.backend.engine.begin() as conn:
            self.library.sql(
                conn,
                "INSERT INTO jobs(id,status,kind,payload,logs,attempts) VALUES (:id,'queued','local-intake',CAST(:payload AS jsonb),'[]',0) ON CONFLICT(id) DO NOTHING",
                id=job_id,
                payload=json.dumps(payload),
            )
        return self.queue.get(job_id)

    def submit_scope(
        self, scope, name, kind, config=None, expert_context=None, bindings=None
    ):
        return self.queue.submit(
            "local-scope",
            self.scope_payload(scope, name, kind, config, expert_context, bindings),
        )

    def scope_payload(
        self, scope, name, kind, config=None, expert_context=None, bindings=None
    ):
        descriptor, _ = processor(self.root, name, kind)
        from osii.domain.processor_settings import merged_processor_settings
        from osii.domain.tool_actions import validate_tool_config
        from osii.configuration import resolve_tool_models

        config = merged_processor_settings(self.root, name, config or {})
        validate_tool_config(descriptor.config_schema, config)
        bindings = resolve_tool_models(
            name, descriptor.model_requirements, self.root, bindings or {}
        )
        context_key = (
            "expert-context:"
            + scope.get("scope_type", "root")
            + ":"
            + str(
                scope.get("file_id")
                or scope.get("folder_id")
                or scope.get("collection_id")
                or "root"
            )
        )
        if expert_context is not None and (
            not isinstance(expert_context, str) or len(expert_context) > 20000
        ):
            raise ValueError("Expert context must be text of at most 20,000 characters")
        if expert_context and expert_context.strip():
            self.library.set_setting(context_key, expert_context.strip())
        else:
            expert_context = self.library.setting(context_key)
        read_scope = self.library.scope(scope)
        docs = []
        source_inputs = []
        for document in self.library.documents(scope):
            representation = self.backend.reader.get_representation(document.file_id)
            source_inputs.append(
                {
                    "file_id": document.file_id,
                    "filename": document.filename,
                    "source_relpath": document.source_relpath,
                    "has_text": bool(representation and representation.text.strip()),
                    "full_chars": len(representation.text) if representation else 0,
                }
            )
            if representation and representation.text.strip():
                docs.append(
                    {
                        "file_id": document.file_id,
                        "filename": document.filename,
                        "source_relpath": document.source_relpath,
                        "text": representation.text,
                        "extraction_id": representation.representation_id,
                        "source_sha256": text_digest(representation.text),
                    }
                )
        if not docs:
            raise ValueError("This scope has no saved text to process")
        from osii.domain.processing.scope_batches import (
            input_batches,
            coverage,
            BatchLimits,
        )

        limits = BatchLimits(
            characters=min(
                100000,
                int(config.get("max_input_chars", 100000)),
                int(config.get("window_chars", 100000)),
            )
        )
        batches = [
            {
                "id": f"map-{index}",
                "ordinal": index,
                "phase": "map",
                "level": 0,
                "inputs": rows,
                "source_ranges": coverage(rows),
                "result": None,
            }
            for index, rows in enumerate(input_batches(docs, limits))
        ]
        revision = ScopeInputRevision.capture(
            self.backend.reader, [doc.file_id for doc in self.library.documents(scope)]
        )
        # Capture again after reading to reject a concurrent edit during staging.
        if any(
            row["source_sha256"]
            != next(
                r.text_sha256 for r in revision.inputs if r.file_id == row["file_id"]
            )
            for row in docs
        ):
            raise ValueError("Scope text changed while staging; try again")
        payload = {
            "workflow": "tool",
            "scope": scope,
            "read_scope": asdict(read_scope),
            "tool_id": name,
            "tool_label": descriptor.display_name,
            "processor_kind": kind,
            "descriptor": descriptor.model_dump(mode="json"),
            "source_documents": docs,
            "source_inputs": source_inputs,
            "input_revision": asdict(revision),
            "expert_context": expert_context,
            "model_bindings": bindings,
            "config": config or {},
            "batches": batches,
            "items": [{"display": row["id"], "status": "pending"} for row in batches],
            "configuration_stamp": configuration_stamp(self.root),
            "batch_progress": {
                "map_batches": len(batches),
                "completed_batches": 0,
                "reduce_batches": 0,
                "text_characters": sum(len(row["text"]) for row in docs),
                "processed_characters": 0,
                "documents": len(source_inputs),
                "completed_documents": 0,
                "documents_with_text": len(docs),
                "documents_without_text": len(source_inputs) - len(docs),
                "batch_characters": limits.characters,
                "reduction": descriptor.capabilities.batch_reduction,
                "phase": "map",
            },
        }
        return payload

    def _update(self, lease, mutate):
        if self.task_index is not None:
            return self._update_root(
                lease, lambda payload: mutate(payload["tasks"][self.task_index])
            )
        return self._update_root(lease, mutate)

    def _update_root(self, lease, mutate):
        with self.backend.engine.begin() as conn:
            row = self.queue._owned(conn, lease)
            payload = dict(row["payload"])
            mutate(payload)
            self.queue._sql(
                conn,
                "UPDATE jobs SET payload=CAST(:payload AS jsonb) WHERE id=:id",
                id=lease.job_id,
                payload=json.dumps(payload, ensure_ascii=False),
            )

    def log(self, lease, message):
        with self.backend.engine.begin() as conn:
            row = self.queue._owned(conn, lease)
            logs = [*row["logs"], f"{now()} {message}"][-2000:]
            self.queue._sql(
                conn,
                "UPDATE jobs SET logs=CAST(:logs AS jsonb) WHERE id=:id",
                id=lease.job_id,
                logs=json.dumps(logs),
            )

    def _checkpoint(self, lease, index, item):
        return JobCheckpoint(
            lease.job_id, lease.worker_id, index, item, generation=lease.generation
        )

    def step(self, lease):
        """One file or bounded model call, then release for pause/cancel checks."""
        state = self.queue.checkpoint(lease)
        if state.state != "running":
            return
        if state.payload.get("configuration_stamp") != configuration_stamp(self.root):
            raise ValueError("Processor/model configuration changed; stage a new run")
        if self._budget_pause(lease, state.payload):
            return
        self._update(lease, lambda payload: payload.setdefault("started_at", now()))
        if state.kind == "local-scope":
            return self.scope_step(lease, state.payload)
        items, options = state.payload["items"], state.payload["options"]
        index = next(
            (i for i, row in enumerate(items) if row["status"] != "done"), None
        )
        if index is not None:
            item = dict(items[index])
            item.update(status="running", started_at=item.get("started_at") or now())
            self.queue.checkpoint(lease, index=index, item=item)
            try:
                self.process_file(
                    lease, index, item, options, staging=state.payload.get("staging")
                )
            except Exception:
                item.update(
                    status="error",
                    error="Processing failed; see the run log.",
                    finished_at=now(),
                )
                self.queue.checkpoint(lease, index=index, item=item)
                raise
            item.update(status="done", error=None, finished_at=now())
            item["duration_seconds"] = max(
                0,
                (
                    datetime.fromisoformat(item["finished_at"])
                    - datetime.fromisoformat(item["started_at"])
                ).total_seconds(),
            )
            state = self.queue.checkpoint(lease, index=index, item=item)
            if state.state == "running":
                self.queue.finish(lease, reschedule=True)
            return
        # All source files are now browsable. Subsequent optional work remains
        # part of this same cancellable/resumable run, not detached child jobs.
        tasks = state.payload.get("tasks", [])
        for index, task in enumerate(tasks):
            if task.get("complete"):
                continue
            self.task_index = index
            try:
                return self.scope_step(lease, task)
            finally:
                self.task_index = None
        # Embeddings are a backfill after all completed files are browsable.
        if options.get("build_embeddings"):
            if options.get("rebuild_embeddings") and not state.payload.get(
                "embedding_reset_done"
            ):
                with self.backend.engine.begin() as conn:
                    current = self.queue._owned(conn, lease)
                    self.library.sql(
                        conn, "UPDATE chunks SET embedding=NULL,embedding_model=NULL"
                    )
                    self.library.sql(
                        conn,
                        "UPDATE documents SET metadata=(metadata-'embedding_identity'-'embedding_model') || jsonb_build_object('stale',COALESCE(metadata->'stale','{}'::jsonb)||jsonb_build_object('embeddings',true)) WHERE active",
                    )
                    self.library.sql(
                        conn,
                        "UPDATE datasets SET revision=revision+1 WHERE id='shared'",
                    )
                    body = {**current["payload"], "embedding_reset_done": True}
                    self.library.sql(
                        conn,
                        "UPDATE jobs SET payload=CAST(:body AS jsonb) WHERE id=:id",
                        id=lease.job_id,
                        body=json.dumps(body),
                    )
                self.queue.finish(lease, reschedule=True)
                return
            for index, item in enumerate(items):
                if item.get("steps", {}).get("embedding") == "done":
                    continue
                if self.embed(lease, index, dict(item), options) is False:
                    return
                self.queue.finish(lease, reschedule=True)
                return
        self._update(lease, lambda payload: payload.update(finished_at=now()))
        self.queue.finish(lease)

    def _budget_pause(self, lease, payload):
        budget = (payload.get("staging") or {}).get("max_seconds")
        if not budget:
            return False
        started = payload.get("budget_started_at")
        if started is None:
            self._update_root(lease, lambda p: p.update(budget_started_at=time.time()))
            return False
        if time.time() - started < budget:
            return False
        self.log(
            lease,
            "Time budget reached between operations; resume to continue the frozen selection.",
        )
        self._update_root(lease, lambda p: p.pop("budget_started_at", None))
        self.queue.finish(lease, outcome="paused")
        return True

    def process_file(self, lease, index, item, options, *, staging=None):
        path = Path(item["path"])
        if staging:
            from osii.volume.staging import validate_member

            validate_member(staging, staging["members"][index])
        limit = int(
            os.getenv("OSII_PROCESSOR_MAX_SOURCE_BYTES", str(250 * 1024 * 1024))
        )
        if limit < 1 or path.stat().st_size > limit:
            raise ValueError(
                "Source exceeds the configured Processor API request limit; select a smaller file or explicitly increase OSII_PROCESSOR_MAX_SOURCE_BYTES"
            )
        content = path.read_bytes()
        if len(content) > limit:
            raise ValueError(
                "Source grew beyond the Processor API request limit while reading"
            )
        if staging:
            validate_member(staging, staging["members"][index])
        sha = hashlib.sha256(content).hexdigest()
        file_id = "sha256-" + sha
        expected = options.get("expected_file_ids", {}).get(str(path))
        if expected and expected != file_id:
            raise ValueError(
                "The selected original changed after staging; rescan before re-extracting"
            )
        if item.get("file_id") not in {None, file_id}:
            raise ValueError("Source content changed during this run; stage it again")
        item["file_id"] = file_id
        previous = self.backend.reader.get_document(file_id)
        read = options.get("run_extraction", True) and (
            options.get("extract_mode") != "missing" or previous is None
        )
        if read and item["steps"].get("extraction") != "done":
            from osii.domain.processing.extractor_selection import load_extractor_routes
            from osii.api.runs_routes import choose_parser_chain

            names = [options.get("extractor_overrides", {}).get(path.suffix.lower())]
            if not names[0]:
                names = choose_parser_chain(path, load_extractor_routes())
            failures = []
            for name in names:
                try:
                    descriptor, client = processor(self.root, name, "extractor")
                    request_id = f"{lease.job_id}:{index}:extract"
                    from osii.domain.processor_settings import merged_processor_settings
                    from osii.domain.tool_actions import validate_tool_config

                    config = merged_processor_settings(
                        self.root,
                        descriptor.name,
                        options.get("extractor_config") or {},
                    )
                    validate_tool_config(descriptor.config_schema, config)
                    request = ExtractionRequest(
                        request_id=request_id,
                        document=DocumentInput(
                            file_id=file_id,
                            filename=path.name,
                            media_type=mimetypes.guess_type(path.name)[0]
                            or "application/octet-stream",
                            content_base64=base64.b64encode(content).decode(),
                        ),
                        config=config,
                        expert_context=options.get("context"),
                    )
                    with model_request(self.root, descriptor, request_id) as context:
                        request = request.model_copy(
                            update={
                                "model_context": ModelContext.model_validate(context)
                                if context
                                else None
                            }
                        )
                        response = client.extract(request)
                    break
                except Exception as exc:
                    failures.append(f"{name}: {type(exc).__name__}")
            else:
                raise ValueError("No extractor succeeded: " + "; ".join(failures))
            primary = options.get("extraction_policy", "make_primary") != "save_variant"
            source = SourceRecord(
                file_id,
                item["source_relpath"],
                path.name,
                request.document.media_type,
                sha,
                len(content),
                {
                    "source_absolute_path": str(path.resolve()),
                    "extraction_document_metadata": response.document_metadata,
                    "file": {
                        "mtime_utc": iso_mtime_utc(path),
                        "birthtime_utc": iso_birthtime_utc(path),
                    },
                },
            )
            command = ProcessingCommit(
                request_id,
                file_id,
                request,
                response,
                descriptor,
                source=source,
                make_primary=primary,
            )
            text, spans = extraction_material(command)
            chunks = chunk_rows(
                file_id,
                text,
                spans,
                method=options.get("chunking_method", "sentence_window"),
                size=int(options.get("chunk_size", 768)),
                overlap=int(options.get("chunk_overlap", 128)),
            )
            command = replace(command, chunks=chunks)
            item["steps"]["extraction"] = "done"
            if staging:
                validate_member(staging, staging["members"][index])
            self.backend.committer.commit(
                command, checkpoint=self._checkpoint(lease, index, item)
            )
            self.log(lease, f"Extracted {path.name}; it is now browsable.")
        elif previous is None:
            raise ValueError(
                "No saved extraction exists; enable extraction for this file"
            )
        if staging:
            validate_member(staging, staging["members"][index])
            member = staging["members"][index]
            with self.backend.engine.begin() as conn:
                self.queue._owned(conn, lease)
                record = self.library.sql(
                    conn,
                    "SELECT metadata FROM documents WHERE file_id=:id FOR UPDATE",
                    id=file_id,
                ).scalar()
                link = {
                    "inventory_database": staging["database"],
                    "entry_id": member["entry_id"],
                    "revision": member["revision"],
                    "run_id": lease.job_id,
                    "updated": time.time(),
                }
                links = [
                    r
                    for r in record.get("inventory_links", [])
                    if (r["inventory_database"], r["entry_id"], r["revision"])
                    != (link["inventory_database"], link["entry_id"], link["revision"])
                ]
                self.library.sql(
                    conn,
                    "UPDATE documents SET metadata=CAST(:meta AS jsonb) WHERE file_id=:id",
                    id=file_id,
                    meta=json.dumps({**record, "inventory_links": [*links, link]}),
                )
        item["steps"].setdefault("extraction", "skipped")
        for key, kind in (
            ("synthesizer_name", "synthesizer"),
            ("enricher_name", "enricher"),
        ):
            if options.get(key) and item["steps"].get(kind) not in {"queued", "done"}:
                task = self.scope_payload(
                    {"scope_type": "object", "file_id": file_id},
                    options[key],
                    kind,
                    options.get(
                        "synthesizer_config"
                        if kind == "synthesizer"
                        else "enricher_config",
                        {},
                    ),
                    options.get("context"),
                )
                task_id = hashlib.sha256(
                    f"{file_id}:{kind}:{options[key]}".encode()
                ).hexdigest()[:20]
                task.update(
                    task_id=task_id,
                    file_item_index=index,
                    step_kind=kind,
                    complete=False,
                )
                for batch in task["batches"]:
                    batch["id"] = task_id + "-" + batch["id"]

                def add(payload):
                    tasks = payload.setdefault("tasks", [])
                    if not any(row["task_id"] == task_id for row in tasks):
                        tasks.append(task)

                self._update_root(lease, add)
                item["steps"][kind] = "queued"
                self.queue.checkpoint(lease, index=index, item=item)
        if options.get("collection_id"):
            record = self.backend.collections.get(options["collection_id"])
            if record is None:
                raise ValueError("Destination collection no longer exists")
            if file_id not in record.member_ids:
                self.backend.collections.replace_members(
                    record.collection_id,
                    (*record.member_ids, file_id),
                    expected_version=record.version,
                )

    def embed(self, lease, index, item, options):
        descriptor, client = processor(self.root, options["embedder_name"], "embedder")
        from osii.domain.model_provider_config import selected_model

        model = options.get("embedding_model") or selected_model(
            "embedder", osii_root=self.root
        )
        binding = embedding_binding(
            self.root, descriptor, getattr(client, "base_url", "")
        )
        chunking = {
            "method": options.get("chunking_method", "sentence_window"),
            "size": int(options.get("chunk_size", 768)),
            "overlap": int(options.get("chunk_overlap", 128)),
        }
        existing = self.backend.reader.get_document(item["file_id"]).metadata.get(
            "embedding_identity"
        )
        if existing:
            from osii.domain.processing.capability_readiness import _model_name_matches

            same_model = (
                _model_name_matches(existing.get("model", ""), model)
                if descriptor.name == "ollama.embedder"
                else existing.get("model") == model
            )
            if (
                not same_model
                or existing.get("connection_fingerprint") != binding
                or existing.get("chunking") != chunking
            ):
                raise ValueError(
                    "Embedding connection, model or chunking changed; explicitly rebuild the index"
                )
        revision = InputRevision.capture(self.backend.reader, item["file_id"])
        representation = self.backend.reader.get_representation(item["file_id"])
        # Chunk rebuilding is explicit within a selected embedding step. A
        # changed text revision cannot retain old offsets or old vector data.
        spans = [
            {
                "id": s.segment_id,
                "char_start": s.char_start,
                "char_end": s.char_end,
                "source_origin": s.source_origin,
            }
            for s in representation.segments
        ]
        chunks = chunk_rows(
            item["file_id"],
            representation.text,
            spans,
            method=options.get("chunking_method", "sentence_window"),
            size=int(options.get("chunk_size", 768)),
            overlap=int(options.get("chunk_overlap", 128)),
        )
        with self.backend.engine.begin() as conn:
            self.queue._owned(conn, lease)
            current = (
                self.library.sql(
                    conn,
                    "SELECT text,metadata FROM documents WHERE file_id=:id FOR UPDATE",
                    id=item["file_id"],
                )
                .mappings()
                .one()
            )
            preferred = (
                current["metadata"]
                .get("edited_representation", {})
                .get("text", current["text"])
            )
            if text_digest(preferred) != revision.text_sha256:
                raise ValueError("Preferred text changed while chunking")
            self.library.sql(
                conn, "DELETE FROM chunks WHERE file_id=:id", id=item["file_id"]
            )
            metadata = {
                **current["metadata"],
                "stale": {**current["metadata"].get("stale", {}), "embeddings": True},
            }
            self.library.sql(
                conn,
                "UPDATE documents SET metadata=CAST(:meta AS jsonb) WHERE file_id=:id",
                id=item["file_id"],
                meta=json.dumps(metadata),
            )
            for chunk in chunks:
                self.library.sql(
                    conn,
                    """INSERT INTO chunks(chunk_id,file_id,text,char_start,char_end,source_origin)
                    VALUES (:chunk_id,:file_id,:text,:char_start,:char_end,CAST(:source_origin AS jsonb))""",
                    **{**chunk, "source_origin": json.dumps(chunk["source_origin"])},
                )
        # Bounded HTTP requests; preserve input order. Publish only a complete
        # validated document response, never a mixture of providers/models.
        vectors, identity = [], None
        from osii.domain.storage.commits import embedding_identity

        cache = item.get("embedding_checkpoint") or {
            "input_revision": asdict(revision),
            "binding": binding,
            "batches": {},
        }
        if cache["input_revision"] != asdict(revision) or cache["binding"] != binding:
            raise ValueError(
                "Text or embedding connection changed; stage a new run instead of reusing incompatible vectors"
            )
        from osii.processor_sdk import EmbeddingResponse

        for offset in range(0, len(chunks), 64):
            request = EmbeddingRequest(
                request_id=f"{lease.job_id}:{index}:embedding:{offset}",
                inputs=[
                    EmbeddingInput(id=row["chunk_id"], text=row["text"])
                    for row in chunks[offset : offset + 64]
                ],
                config={"model": model},
            )
            saved = cache["batches"].get(str(offset))
            if saved:
                response = EmbeddingResponse.model_validate(saved)
            else:
                with model_request(
                    self.root, descriptor, request.request_id
                ) as context:
                    request = request.model_copy(
                        update={
                            "model_context": ModelContext.model_validate(context)
                            if context
                            else None
                        }
                    )
                    response = client.embed(request)
                response = response.model_copy(
                    update={
                        "metadata": {
                            **response.metadata,
                            "connection_fingerprint": binding,
                            "chunking": chunking,
                        }
                    }
                )
            if descriptor.name == "ollama.embedder":
                from osii.domain.processing.capability_readiness import (
                    _model_name_matches,
                )

                if _model_name_matches(response.model, model):
                    request = request.model_copy(
                        update={"config": {**request.config, "model": response.model}}
                    )
            ProcessingCommit(
                request.request_id,
                item["file_id"],
                request,
                response,
                descriptor,
                input_revision=revision,
                chunks=chunks[offset : offset + 64],
            ).validate()
            current = embedding_identity(response)
            if existing and current != existing:
                raise ValueError(
                    "Embedding vector space changed; explicitly rebuild the index"
                )
            if identity is not None and current != identity:
                raise ValueError(
                    "Embedding provider/model/dimensions changed during indexing"
                )
            identity = current
            vectors.extend(response.vectors)
            if not saved:
                cache["batches"][str(offset)] = response.model_dump(mode="json")
                item["embedding_checkpoint"] = cache
                state = self.queue.checkpoint(lease, index=index, item=item)
                if state.state != "running":
                    return False
                if self._budget_pause(lease, state.payload):
                    return False
        if not chunks:
            raise ValueError("No usable text chunks to embed")
        request = EmbeddingRequest(
            request_id=f"{lease.job_id}:{index}:embedding",
            inputs=[
                EmbeddingInput(id=row["chunk_id"], text=row["text"]) for row in chunks
            ],
            config={"model": response.model},
        )
        response = response.model_copy(
            update={"request_id": request.request_id, "vectors": vectors}
        )
        item["steps"]["embedding"] = "done"
        item.pop("embedding_checkpoint", None)
        if self.queue.get(lease.job_id).payload.get(
            "configuration_stamp"
        ) != configuration_stamp(self.root):
            raise ValueError(
                "Model or processor configuration changed while embedding; stage a new run"
            )
        command = ProcessingCommit(
            request.request_id,
            item["file_id"],
            request,
            response,
            descriptor,
            input_revision=revision,
            chunks=chunks,
        )
        self.backend.committer.commit(
            command, checkpoint=self._checkpoint(lease, index, item)
        )
        self.log(lease, f"Indexed {item['display']} with {response.model}.")
        return True

    def scope_step(self, lease, payload):
        from osii.domain.processing.scope_batches import (
            normalize_result,
            request_scope,
            reduction_groups,
            reduction_inputs,
        )

        descriptor = ProcessorDescriptor.model_validate(payload["descriptor"])
        current_descriptor, client = processor(
            self.root, descriptor.name, payload["processor_kind"]
        )
        if current_descriptor != descriptor:
            raise ValueError("Processor descriptor changed; stage a new run")
        batches = payload["batches"]
        pending = next((row for row in batches if row["result"] is None), None)
        if pending is None and descriptor.capabilities.batch_reduction == "wiki":
            level = max(row["level"] for row in batches)
            last = [row for row in batches if row["level"] == level]
            if len(last) > 1:
                reductions = []
                from osii.domain.processing.scope_batches import BatchLimits

                for index, children in enumerate(
                    reduction_groups(
                        last,
                        BatchLimits(
                            characters=payload["batch_progress"]["batch_characters"]
                        ),
                    )
                ):
                    prefix = payload.get("task_id", "")
                    reductions.append(
                        {
                            "id": (prefix + "-" if prefix else "")
                            + f"reduce-{level + 1}-{index}",
                            "ordinal": index,
                            "phase": "reduce",
                            "level": level + 1,
                            "inputs": reduction_inputs(children),
                            "source_ranges": [],
                            "result": children[0]["result"]
                            if len(children) == 1
                            else None,
                        }
                    )
                if len(reductions) >= len(last):
                    raise ValueError(
                        "Wiki outputs exceed the reduction budget; use shorter outputs"
                    )
                self._update(lease, lambda p: p["batches"].extend(reductions))
                self.queue.finish(lease, reschedule=True)
                return
        if pending:
            request_id = f"{lease.job_id}:{pending['id']}"
            cls = (
                SynthesisRequest
                if payload["processor_kind"] == "synthesizer"
                else EnrichmentRequest
            )
            with model_request(
                self.root, descriptor, request_id, payload.get("model_bindings")
            ) as context:
                request = cls(
                    request_id=request_id,
                    scope=request_scope(
                        payload["scope"],
                        pending["inputs"],
                        phase=pending["phase"],
                        batch_id=pending["id"],
                    ),
                    config=payload["config"],
                    expert_context=payload.get("expert_context"),
                    model_context=context,
                )
                response = (
                    client.synthesize(request)
                    if payload["processor_kind"] == "synthesizer"
                    else client.enrich(request)
                )
            if hasattr(response, "request_id") and (
                response.request_id != request.request_id
                or response.processor != descriptor
            ):
                raise ValueError("Processor returned a mismatched batch response")
            result = normalize_result(
                response, pending["inputs"], derived=pending["phase"] == "reduce"
            )

            def save(p):
                row = next(row for row in p["batches"] if row["id"] == pending["id"])
                row["result"] = result
                if hasattr(response, "metadata"):
                    row["processor_metadata"] = response.metadata
                progress = p["batch_progress"]
                if row["phase"] == "map":
                    progress["completed_batches"] += 1
                    progress["processed_characters"] += sum(
                        len(r["text"]) for r in row["inputs"]
                    )
                    progress["completed_documents"] += sum(
                        r["char_end"] == r["full_chars"] for r in row["inputs"]
                    )
                    p["items"][row["ordinal"]]["status"] = "done"
                else:
                    progress["reduce_batches"] += 1
                progress["phase"] = row["phase"]

            self._update(lease, save)
            self.log(
                lease,
                f"Saved {pending['id']}; completed calls will be reused on retry.",
            )
            state = self.queue.checkpoint(lease)
            if state.state == "running":
                self.queue.finish(lease, reschedule=True)
            return
        self.publish_scope(lease, payload, descriptor)
        if self.task_index is None:
            self._update(lease, lambda payload: payload.update(finished_at=now()))
            self.queue.finish(lease)
        else:
            task_index = self.task_index

            def done(payload):
                task = payload["tasks"][task_index]
                task["complete"] = True
                payload["items"][task["file_item_index"]]["steps"][
                    task["step_kind"]
                ] = "done"

            self._update_root(lease, done)
            self.queue.finish(lease, reschedule=True)

    def publish_scope(self, lease, payload, descriptor):
        from osii.domain.processing.scope_batches import (
            publication_outputs,
            sampled_keywords,
        )
        from osii.processor_sdk import EnrichmentResponse, SynthesisResponse, Artifact

        read_scope = ReadScope(**payload["read_scope"])
        revision = ScopeInputRevision.from_dict(payload["input_revision"])
        batches = payload["batches"]
        operation = lease.job_id + ":" + payload.get("task_id", "standalone")
        last = [
            row for row in batches if row["level"] == max(r["level"] for r in batches)
        ]
        final = (
            last[0]["result"]
            if descriptor.capabilities.batch_reduction == "wiki"
            else None
        )
        outputs = publication_outputs(
            lease.job_id,
            payload["batch_progress"],
            descriptor.display_name,
            final,
            batches[0]["result"],
        )
        if descriptor.name == "stats_keywords":
            from collections import Counter

            counts = Counter()
            for batch in batches:
                if batch["phase"] != "map":
                    continue
                for artifact in batch["result"].get("artifacts", []):
                    for row in artifact["data"].get("rows", []):
                        if "term" in row and "count" in row:
                            counts[row["term"]] += row["count"]
            minimum = max(1, int(payload["config"].get("min_count", 1)))
            top = max(1, int(payload["config"].get("top_k", 20)))
            rows = [
                {"term": term, "count": count}
                for term, count in sorted(counts.items(), key=lambda r: (-r[1], r[0]))
                if count >= minimum
            ][:top]
            outputs = [
                row for row in outputs if row["id"] != "keywords--stats_keywords"
            ]
            outputs.append(
                {
                    "id": "keywords--stats_keywords",
                    "family": "enrichment",
                    "data": {
                        "artifact_type": "table",
                        "title": "Keyword frequencies",
                        "description": "Counts combined across all text batches before ranking.",
                        "columns": [
                            {"key": "term", "label": "Term", "data_type": "string"},
                            {"key": "count", "label": "Count", "data_type": "integer"},
                        ],
                        "rows": rows,
                    },
                }
            )
        # Publication uses full frozen texts solely for Core's revision/citation
        # validation. Processors only saw the bounded per-batch requests above.
        scope = ScopeInput(
            scope_type=read_scope.kind,
            scope_id=read_scope.identifier,
            documents=[
                DocumentInput(
                    file_id=row["file_id"], filename=row["filename"], text=row["text"]
                )
                for row in payload["source_documents"]
            ],
        )
        standard = [
            row
            for row in outputs
            if row["data"].get("artifact_type")
            in {"table", "entity_list", "knowledge_graph", "wiki_markdown"}
        ]
        # Old Core enrichers add convenience keys beyond Processor API models.
        # Keep their raw output in batch history, validate standard views at commit.
        from osii.processor_sdk import (
            TableArtifactData,
            EntityListArtifactData,
            KnowledgeGraphArtifactData,
            WikiMarkdownArtifactData,
        )

        types = {
            "table": TableArtifactData,
            "entity_list": EntityListArtifactData,
            "knowledge_graph": KnowledgeGraphArtifactData,
            "wiki_markdown": WikiMarkdownArtifactData,
        }
        standard = [
            {
                **row,
                "data": {
                    k: v
                    for k, v in row["data"].items()
                    if k in types[row["data"]["artifact_type"]].model_fields
                },
            }
            for row in standard
        ]
        from osii.configuration import model_connection

        targets = {
            cap: {
                "alias": alias,
                "model": (model_connection(alias, self.root) or {}).get("model"),
            }
            for cap, alias in (payload.get("model_bindings") or {}).items()
        }
        provenance = {
            "run_id": lease.job_id,
            "model_targets": targets,
            "batch_processor_metadata": [
                row.get("processor_metadata", {}) for row in batches
            ],
        }
        if payload["processor_kind"] == "synthesizer":
            markdown = next(
                (
                    row["data"].get("markdown")
                    for row in standard
                    if row["data"].get("artifact_type") == "wiki_markdown"
                ),
                "",
            )
            if markdown:
                citations = next(
                    row["data"].get("citations", [])
                    for row in standard
                    if row["data"].get("artifact_type") == "wiki_markdown"
                )
                request = SynthesisRequest(
                    request_id=operation,
                    scope=scope,
                    config=payload["config"],
                    expert_context=payload.get("expert_context"),
                )
                response = SynthesisResponse(
                    request_id=operation,
                    processor=descriptor,
                    markdown=markdown,
                    citations=citations,
                )
                self.backend.committer.commit(
                    ScopeProcessingCommit(
                        operation,
                        read_scope,
                        request,
                        response,
                        descriptor,
                        revision,
                        provenance,
                    ),
                    checkpoint=JobCheckpoint(
                        lease.job_id, lease.worker_id, generation=lease.generation
                    ),
                )
        elif standard:
            request = EnrichmentRequest(
                request_id=operation,
                scope=scope,
                config=payload["config"],
                expert_context=payload.get("expert_context"),
            )
            response = EnrichmentResponse(
                request_id=operation,
                processor=descriptor,
                artifacts=[
                    Artifact(
                        id=row["id"],
                        kind=row["data"]["artifact_type"],
                        media_type="application/json",
                        standard_data=row["data"],
                    )
                    for row in standard
                ],
            )
            self.backend.committer.commit(
                ScopeProcessingCommit(
                    operation,
                    read_scope,
                    request,
                    response,
                    descriptor,
                    revision,
                    provenance,
                ),
                checkpoint=JobCheckpoint(
                    lease.job_id, lease.worker_id, generation=lease.generation
                ),
            )
        # The batch-run manifest is a Core operational product, not a new private
        # processor output format. Keep its publication transaction revision-safe.
        with self.backend.engine.begin() as conn:
            self.library.sql(conn, "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            self.queue._owned(conn, lease)
            current = self.backend.committer._scope_current(
                conn, read_scope, None, len(revision.member_ids) + 1
            )
            revision.verify_current(current)
            name = f"batch-results--{descriptor.name}.json"
            product_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"osii-batches:{read_scope.kind}:{read_scope.identifier}:{name}",
                )
            )
            self.library.sql(
                conn,
                """INSERT INTO scope_products(id,scope_type,scope_id,filename,family,method,title,artifact_type)
                VALUES (:id,:kind,:scope,:name,'enrichment',:method,:title,'scope_batch_run')
                ON CONFLICT ON CONSTRAINT scope_product_address DO NOTHING""",
                id=product_id,
                kind=read_scope.kind,
                scope=read_scope.identifier,
                name=name,
                method=descriptor.name,
                title=descriptor.display_name,
            )
            product = (
                self.library.sql(
                    conn,
                    "SELECT * FROM scope_products WHERE id=:id FOR UPDATE",
                    id=product_id,
                )
                .mappings()
                .one()
            )
            data = next(
                row["data"]
                for row in outputs
                if row["data"]["artifact_type"] == "scope_batch_run"
            )
            if payload.get("task_id"):
                data["task_id"] = payload["task_id"]
            data["keyword_samples"] = sampled_keywords(
                [r for r in batches if r["phase"] == "map"]
            )
            rid = str(uuid.uuid5(uuid.NAMESPACE_URL, "osii-batch-result:" + operation))
            provenance = {
                "run_id": lease.job_id,
                "processor": descriptor.model_dump(mode="json"),
                "processing_input": payload["input_revision"],
            }
            self.library.sql(
                conn,
                """INSERT INTO scope_revisions VALUES (:id,:product,:parent,'generated',:created,NULL,
                CAST(:data AS jsonb),CAST(:provenance AS jsonb)) ON CONFLICT(id) DO NOTHING""",
                id=rid,
                product=product_id,
                parent=product["current_revision"],
                created=now(),
                data=json.dumps(data),
                provenance=json.dumps(provenance),
            )
            origin = self.library.sql(
                conn,
                "SELECT origin FROM scope_revisions WHERE id=:id",
                id=product["current_revision"],
            ).scalar()
            if origin != "human":
                self.library.sql(
                    conn,
                    "UPDATE scope_products SET current_revision=:revision WHERE id=:id",
                    id=product_id,
                    revision=rid,
                )


def run_worker(backend):
    import signal
    from osii.domain.storage.postgres_library import PostgresLibrary

    workflow = PostgresWorkflow(PostgresLibrary(backend))
    worker_id = "local-pg-" + uuid.uuid4().hex
    stop = threading.Event()
    active_lease = None

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    handled_signals = [signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        handled_signals.append(signal.SIGBREAK)
    previous = {sig: signal.signal(sig, interrupt) for sig in handled_signals}

    def heartbeat():
        while not stop.wait(3):
            try:
                workflow.library.set_setting("local_worker", {"heartbeat": time.time()})
            except Exception:
                pass

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        workflow.library.set_setting("local_worker", {"heartbeat": time.time()})
        while True:
            claim = backend.jobs.claim(worker_id)
            if claim is None:
                time.sleep(0.5)
                continue
            lease_stop = threading.Event()
            active_lease = claim.lease

            def renew():
                while not lease_stop.wait(3):
                    try:
                        backend.jobs.heartbeat(claim.lease)
                    except Exception:
                        return

            renewal = threading.Thread(target=renew, daemon=True)
            renewal.start()
            try:
                workflow.step(claim.lease)
            except JobOwnershipLost:
                pass
            except Exception as exc:
                # Domain messages are bounded; upstream request bodies and
                # credentials never become public run logs.
                message = (
                    str(exc)[:1000]
                    if type(exc) is ValueError
                    else f"{type(exc).__name__}: processing failed; check the service logs"
                )
                try:
                    backend.jobs.finish(claim.lease, error=message)
                except JobOwnershipLost:
                    pass
            finally:
                lease_stop.set()
                renewal.join(timeout=2)
                if not isinstance(sys.exc_info()[1], KeyboardInterrupt):
                    active_lease = None
    except KeyboardInterrupt:
        pass
    finally:
        if active_lease is not None:
            try:
                backend.jobs.finish(active_lease, reschedule=True)
            except JobOwnershipLost:
                pass
        stop.set()
        thread.join(timeout=2)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        backend.close()
