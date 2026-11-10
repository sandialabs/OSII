"""PostgreSQL persistence and worker adapter for lossless scope-tool batches."""

from __future__ import annotations
import hashlib
from sqlalchemy import select, insert, update, func
from sqlalchemy.dialects.postgresql import insert as upsert
from osii.persistence.postgres import documents, jobs, identifier, now
from osii.persistence.workspace_schema import (
    scope_tool_batches as batches,
    scope_tool_sources as sources,
)
from osii.persistence.scope_products import ScopeProducts, address
from osii.domain.processing.scope_batches import (
    input_batches,
    coverage,
    execute_batches,
    request_scope,
    reduction_inputs,
    BatchLimits,
)
from osii.server.intake import configuration_stamp
from osii.server.processors import catalog, bounded_config, invoke
from osii.processor_sdk import SynthesisRequest, EnrichmentRequest


def submit(store, settings, actor, payload):
    from osii.server.library_tools import scoped_headers, extraction_identity

    scope = payload["scope"]
    kind, _ = address(scope)
    choice = next(
        (
            row
            for row in catalog(store, settings)
            if row.get("id") == payload["enricher_name"]
            and row.get("kind") in {"synthesizer", "enricher"}
        ),
        None,
    )
    if choice is None or not choice["available"]:
        raise ValueError("The selected scope tool is unavailable; check Setup")
    if kind not in choice["descriptor"]["capabilities"]["scope_types"]:
        raise ValueError("The method does not support this scope")
    bindings = payload.get("model_bindings") or {}
    if set(bindings) - {"chat"} or any(
        value not in {"", "server.chat"} for value in bindings.values()
    ):
        raise ValueError("Choose the configured hosted writing model")
    config = bounded_config(payload.get("enricher_config") or {}, choice)
    headers = scoped_headers(store, scope, actor["id"])
    ids = [row["file_id"] for row in headers]
    if not ids:
        raise ValueError("No documents are in this scope")
    stamp = configuration_stamp(store, settings)
    jid = identifier()
    reduction = choice["descriptor"]["capabilities"].get(
        "batch_reduction", "partitioned"
    )
    # These model-backed methods explicitly support combining derived summaries.
    if choice["id"] == "openai.synthesizer":
        reduction = "wiki"
    batch_characters = min(
        100000,
        int(config.get("max_input_chars", 100000)),
        int(config.get("window_chars", 100000)),
    )
    summary = {
        "batch_characters": batch_characters,
        "documents": len(ids),
        "documents_with_text": 0,
        "documents_without_text": 0,
        "text_characters": 0,
        "map_batches": 0,
        "completed_batches": 0,
        "completed_documents": 0,
        "processed_characters": 0,
        "reduce_batches": 0,
        "reduction": reduction,
        "phase": "map",
    }
    body = {
        "batch_version": 1,
        "workflow": "tool",
        "actor_id": actor["id"],
        "scope": scope,
        "selection": choice,
        "config": config,
        "expert_context": payload.get("expert_context") or "",
        "configuration_stamp": stamp,
        "product_parents": ScopeProducts(store).parents(scope, choice["id"]),
        "tool_id": choice["id"],
        "tool_label": choice["display_name"],
        "scope_title": "Library"
        if kind == "root"
        else str(
            scope.get("collection_id")
            or scope.get("folder_id")
            or headers[0]["filename"]
        ),
        "batch_progress": summary,
        "member_ids": ids,
        "items": [{"display": choice["display_name"], "status": "pending"}],
    }
    # One consistent snapshot; no whole-corpus text or vector array enters RAM.
    with store.engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin():
            connection.execute(
                insert(jobs).values(
                    id=jid,
                    kind="tool",
                    status="queued",
                    payload=body,
                    logs=[],
                    attempts=0,
                    created_at=now(),
                )
            )
            rows = (
                connection.execution_options(stream_results=True)
                .execute(
                    select(
                        documents.c.file_id,
                        documents.c.filename,
                        documents.c.media_type,
                        documents.c.source_relpath,
                        documents.c.text,
                        extraction_identity().label("extraction_id"),
                        func.md5(documents.c.text).label("text_fingerprint"),
                    )
                    .where(documents.c.active, documents.c.file_id.in_(ids))
                    .order_by(documents.c.file_id)
                )
                .mappings()
                .yield_per(1)
            )
            connection.execution_options(stream_results=False)

            def texts():
                for raw in rows:
                    row = dict(raw)
                    source = {k: v for k, v in row.items() if k != "text"}
                    source.update(
                        has_text=bool(row["text"].strip()),
                        source_sha256=hashlib.sha256(row["text"].encode()).hexdigest(),
                        full_chars=len(row["text"]),
                    )
                    connection.execute(
                        insert(sources).values(
                            job_id=jid, file_id=row["file_id"], record=source
                        )
                    )
                    if row["text"].strip():
                        summary["documents_with_text"] += 1
                        summary["text_characters"] += len(row["text"])
                    else:
                        summary["documents_without_text"] += 1
                    yield row

            for index, items in enumerate(
                input_batches(texts(), BatchLimits(characters=batch_characters))
            ):
                connection.execute(
                    insert(batches).values(
                        job_id=jid,
                        id=f"map-{index}",
                        ordinal=index,
                        phase="map",
                        level=0,
                        inputs=items,
                        source_ranges=coverage(items),
                        calls={},
                    )
                )
                summary["map_batches"] += 1
            if summary["documents_with_text"] + summary[
                "documents_without_text"
            ] != len(ids):
                raise ValueError(
                    "The scope changed while preparing this run; try again"
                )
            if not summary["map_batches"]:
                raise ValueError("Read document text before running this tool")
            if stamp != configuration_stamp(store, settings):
                raise ValueError(
                    "Configuration changed while freezing this run; try again"
                )
            connection.execute(
                update(jobs).where(jobs.c.id == jid).values(payload=body)
            )
    store.record("scope_tool_queued", actor["id"], jid)
    return {
        "run_id": jid,
        "status": "queued",
        "scope": scope,
        "enricher_name": choice["id"],
        "input_summary": summary,
    }


class HostedBatchStorage:
    def __init__(self, store, job, worker):
        self.store, self.job, self.worker = store, job, worker

    def summary(self):
        return self.store.job(self.job["id"])["payload"]["batch_progress"]

    def reconcile(self):
        pass

    def rows(self, phase, level, pending_only=False):
        after = -1
        while True:
            with self.store.engine.connect() as c:
                row = (
                    c.execute(
                        select(batches)
                        .where(
                            batches.c.job_id == self.job["id"],
                            batches.c.phase == phase,
                            batches.c.level == level,
                            batches.c.ordinal > after,
                            batches.c.result.is_(None) if pending_only else True,
                        )
                        .order_by(batches.c.ordinal)
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                return
            after = row["ordinal"]
            yield dict(row)

    def count(self, phase, level):
        with self.store.engine.connect() as c:
            return c.execute(
                select(func.count()).where(
                    batches.c.job_id == self.job["id"],
                    batches.c.phase == phase,
                    batches.c.level == level,
                )
            ).scalar_one()

    def ensure_reduction(self, level, index, children):
        identity = f"reduce-{level}-{index}"
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (self.job["id"], self.worker))
            statement = upsert(batches).values(
                job_id=self.job["id"],
                id=identity,
                ordinal=index,
                phase="reduce",
                level=level,
                inputs=reduction_inputs(children),
                source_ranges=[{"batch_id": row["id"]} for row in children],
                calls={},
                result=children[0]["result"] if len(children) == 1 else None,
            )
            c.execute(statement.on_conflict_do_nothing())
            return dict(
                c.execute(
                    select(batches).where(
                        batches.c.job_id == self.job["id"], batches.c.id == identity
                    )
                )
                .mappings()
                .one()
            )

    def save_call(self, identity, key, value=None):
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (self.job["id"], self.worker))
            row = c.execute(
                select(batches.c.calls)
                .where(batches.c.job_id == self.job["id"], batches.c.id == identity)
                .with_for_update()
            ).scalar_one()
            if value is None:
                return row.get(key)
            c.execute(
                update(batches)
                .where(batches.c.job_id == self.job["id"], batches.c.id == identity)
                .values(calls={**row, key: value})
            )

    def save_result(self, identity, result):
        with self.store.transaction() as c:
            self.store.assert_job_owner(c, (self.job["id"], self.worker))
            row = (
                c.execute(
                    select(batches)
                    .where(batches.c.job_id == self.job["id"], batches.c.id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["result"] is not None:
                return
            c.execute(
                update(batches)
                .where(batches.c.job_id == self.job["id"], batches.c.id == identity)
                .values(result=result)
            )
            payload = dict(
                c.execute(
                    select(jobs.c.payload).where(jobs.c.id == self.job["id"])
                ).scalar_one()
            )
            progress = payload["batch_progress"]
            progress["phase"] = row["phase"]
            if row["phase"] == "map":
                progress["completed_batches"] += 1
                progress["processed_characters"] += sum(
                    len(item["text"]) for item in row["inputs"]
                )
                progress["completed_documents"] += sum(
                    item["char_end"] == item["full_chars"] for item in row["inputs"]
                )
            else:
                progress["reduce_batches"] += 1
            c.execute(
                update(jobs).where(jobs.c.id == self.job["id"]).values(payload=payload)
            )

    def finish(self, final):
        from osii.domain.processing.scope_batches import publication_outputs

        payload = self.job["payload"]
        summary = self.summary()
        if summary["processed_characters"] != summary["text_characters"]:
            raise ValueError("Not all saved-text characters have completed batches")
        outputs = publication_outputs(
            self.job["id"],
            summary,
            payload["scope_title"] + " · " + payload["tool_label"],
            final,
            next(self.rows("map", 0))["result"],
        )
        from osii.domain.processing.scope_batches import sampled_keywords

        samples = sampled_keywords(self.rows("map", 0))
        for output in outputs:
            if output["data"].get("artifact_type") == "scope_batch_run":
                output["data"]["keyword_samples"] = samples
        provenance = {
            "run_id": self.job["id"],
            "batch_run_id": self.job["id"],
            "scope": payload["scope"],
            "member_ids": payload["member_ids"],
            "tool": payload["tool_id"],
            "input_summary": summary,
            "config": payload["config"],
        }
        ScopeProducts(self.store).generated(
            payload["scope"],
            payload["tool_id"],
            outputs,
            self.job,
            self.worker,
            provenance,
        )


def execute(store, settings, provider, job, worker, stopping, report):
    from osii.server.library_tools import scoped_headers

    payload = job["payload"]
    storage = HostedBatchStorage(store, job, worker)

    def ready():
        if stopping.is_set():
            return False
        if store.checkpoint(job["id"], worker) != "running":
            return False
        actor = store.account(user_id=payload["actor_id"])
        if not actor or not actor["active"] or actor["role"] != "admin":
            raise ValueError("Processing permission was revoked")
        scoped_headers(store, payload["scope"], actor["id"])
        if configuration_stamp(store, settings) != payload["configuration_stamp"]:
            raise ValueError("Configuration changed; restore it to resume this run")
        return True

    def call(row):
        cls = (
            SynthesisRequest
            if payload["selection"]["kind"] == "synthesizer"
            else EnrichmentRequest
        )
        config = dict(payload["config"])
        if payload["tool_id"] == "openai.synthesizer":
            config["extract_metadata"] = False
        guidance = payload["expert_context"]
        if row["phase"] == "reduce":
            guidance = (
                "Combine these derived batch summaries. They are not original evidence. Preserve uncertainty and source identifiers. Do not add facts.\n"
                + guidance
            )
        request = cls(
            request_id=identifier(),
            scope=request_scope(
                payload["scope"], row["inputs"], phase=row["phase"], batch_id=row["id"]
            ),
            config=config,
            expert_context=guidance or None,
        )
        response = invoke(
            store,
            settings,
            provider,
            payload["selection"],
            request,
            job_id=job["id"],
            worker=worker,
            checkpoint=lambda key, value=None: storage.save_call(row["id"], key, value),
        )
        return response.model_validate_json(
            response.model_dump_json().replace("\\u0000", "\\ufffd")
        )

    execute_batches(storage, call, ready, report)
    return stopping.is_set()


def details(store, job_id, *, cursor=0, limit=20):
    with store.engine.connect() as c:
        rows = (
            c.execute(
                select(
                    batches.c.id,
                    batches.c.ordinal,
                    batches.c.phase,
                    batches.c.level,
                    batches.c.source_ranges,
                    batches.c.result.is_not(None).label("done"),
                )
                .where(
                    batches.c.job_id == job_id,
                    batches.c.phase == "map",
                    batches.c.ordinal >= cursor,
                )
                .order_by(batches.c.ordinal)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
    return {
        "items": [
            {**dict(row), "status": "done" if row["done"] else "pending"}
            for row in rows[:limit]
        ],
        "next_cursor": rows[limit - 1]["ordinal"] + 1 if len(rows) > limit else None,
    }


def batch_result(store, job_id, batch_id):
    with store.engine.connect() as c:
        row = (
            c.execute(
                select(batches.c.id, batches.c.source_ranges, batches.c.result).where(
                    batches.c.job_id == job_id, batches.c.id == batch_id
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise KeyError("Batch not found")
    return dict(row)


def input_state(store, scope, job_id, actor_id):
    from osii.server.library_tools import scoped_headers, extraction_identity

    ids = {row["file_id"] for row in scoped_headers(store, scope, actor_id)}
    with store.engine.connect() as connection:
        original = {
            row.file_id: row.record
            for row in connection.execute(
                select(sources.c.file_id, sources.c.record).where(
                    sources.c.job_id == job_id
                )
            )
        }
        if ids != set(original):
            return "stale"
        current = connection.execute(
            select(
                documents.c.file_id,
                extraction_identity().label("extraction_id"),
                func.md5(documents.c.text).label("fingerprint"),
            ).where(documents.c.active, documents.c.file_id.in_(ids))
        )
        if any(
            original[row.file_id]["extraction_id"] != row.extraction_id
            or original[row.file_id]["text_fingerprint"] != row.fingerprint
            for row in current
        ):
            return "stale"
    return "current"


def source_details(store, job_id, *, cursor=0, limit=50, only_missing=False):
    query = select(sources.c.file_id, sources.c.record).where(
        sources.c.job_id == job_id
    )
    if only_missing:
        query = query.where(sources.c.record["has_text"].astext == "false")
    with store.engine.connect() as connection:
        rows = (
            connection.execute(
                query.order_by(sources.c.file_id).offset(cursor).limit(limit + 1)
            )
            .mappings()
            .all()
        )
    return {
        "items": [{"file_id": row["file_id"], **row["record"]} for row in rows[:limit]],
        "next_cursor": cursor + limit if len(rows) > limit else None,
    }
