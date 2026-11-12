"""Standalone sidecar/queue adapter for the shared whole-scope batch engine."""

from __future__ import annotations
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from osii.domain.processing.scope_batches import (
    input_batches,
    coverage,
    execute_batches,
    request_scope,
    reduction_inputs,
    publication_outputs,
    BatchLimits,
)
from osii.domain.processing.jobs import (
    get_run,
    save_run,
    append_log,
    create_run_record,
    enqueue_run,
    honor_run_control,
)
from osii.domain.storage.atomic import atomic_write_text


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, value):
    atomic_write_text(path, json.dumps(value, ensure_ascii=False))


class LocalBatchStorage:
    def __init__(self, root, run_id, job=None):
        self.root, self.run_id, self.job = root, run_id, job
        self.directory = root / "state" / "job-inputs" / run_id

    def guard(self):
        from contextlib import nullcontext
        from osii.domain.processing.jobs import queue_job_write

        return (
            queue_job_write(self.job["id"], self.job["worker_id"])
            if self.job
            else nullcontext()
        )

    def header(self):
        return _read(self.directory / "manifest.json")

    def state(self):
        return _read(self.directory / "progress.json")

    def summary(self):
        return self.state()["summary"]

    def save_header(self, header):
        _save(self.directory / "manifest.json", header)
        _save(
            self.directory / "progress.json",
            {"summary": header["summary"], "levels": header["levels"], "accounted": []},
        )

    def rows(self, phase, level, pending_only=False):
        count = self.state()["levels"].get(f"{phase}:{level}", 0)
        for index in range(count):
            identity = f"map-{index}" if phase == "map" else f"reduce-{level}-{index}"
            result_path = self.directory / f"result-{identity}.json"
            if pending_only and result_path.is_file():
                continue
            row = _read(self.directory / f"{phase}-{level}-{index}.json")
            row["result"] = _read(result_path) if result_path.is_file() else None
            yield row

    def count(self, phase, level):
        return self.state()["levels"].get(f"{phase}:{level}", 0)

    def _path(self, identity):
        if identity.startswith("map-"):
            return self.directory / f"map-0-{int(identity[4:])}.json"
        _, level, index = identity.split("-")
        return self.directory / f"reduce-{int(level)}-{int(index)}.json"

    def ensure_reduction(self, level, index, children):
        identity = f"reduce-{level}-{index}"
        path = self._path(identity)
        if not path.is_file():
            _save(
                path,
                {
                    "id": identity,
                    "ordinal": index,
                    "phase": "reduce",
                    "level": level,
                    "inputs": reduction_inputs(children),
                    "source_ranges": [{"batch_id": row["id"]} for row in children],
                    "calls": {},
                    "result": children[0]["result"] if len(children) == 1 else None,
                },
            )
        state = self.state()
        state["levels"][f"reduce:{level}"] = max(
            state["levels"].get(f"reduce:{level}", 0), index + 1
        )
        _save(self.directory / "progress.json", state)
        if (
            len(children) == 1
            and not (self.directory / f"result-{identity}.json").is_file()
        ):
            _save(self.directory / f"result-{identity}.json", children[0]["result"])
        row = _read(path)
        result_path = self.directory / f"result-{identity}.json"
        row["result"] = _read(result_path) if result_path.is_file() else None
        return row

    def save_call(self, identity, key, value=None):
        path = self._path(identity)
        row = _read(path)
        if value is None:
            return row["calls"].get(key)
        row["calls"][key] = value
        _save(path, row)

    def reconcile(self):
        state = self.state()
        accounted = set(state["accounted"])
        progress = state["summary"]
        changed = False
        for key, count in state["levels"].items():
            phase, level = key.split(":")
            for index in range(count):
                identity = (
                    f"map-{index}" if phase == "map" else f"reduce-{level}-{index}"
                )
                if (
                    identity in accounted
                    or not (self.directory / f"result-{identity}.json").is_file()
                ):
                    continue
                info = (
                    _read(self.directory / f"info-{identity}.json")
                    if phase == "map"
                    else None
                )
                if info:
                    progress["completed_batches"] += 1
                    progress["processed_characters"] += sum(
                        row["char_end"] - row["char_start"]
                        for row in info["source_ranges"]
                    )
                    progress["completed_documents"] += sum(
                        row["char_end"] == row["full_chars"]
                        for row in info["source_ranges"]
                    )
                else:
                    progress["reduce_batches"] += 1
                progress["phase"] = phase
                accounted.add(identity)
                changed = True
        if changed:
            state["accounted"] = sorted(accounted)
            _save(self.directory / "progress.json", state)
            run = get_run(self.run_id)
            run["batch_progress"] = progress
            save_run(run)

    def save_result(self, identity, result):
        path = self.directory / f"result-{identity}.json"
        with self.guard():
            if not path.is_file():
                _save(path, result)
        self.reconcile()

    def keyword_result(self, header):
        import sqlite3

        # A derived accumulator on local disk keeps vocabulary memory bounded.
        with sqlite3.connect(self.directory / "keyword-counts.sqlite3") as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS terms(batch TEXT,term TEXT,frequency INTEGER,PRIMARY KEY(batch,term))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS combined(batch TEXT PRIMARY KEY)"
            )
            for batch in self.rows("map", 0):
                if honor_run_control(self.run_id):
                    return None
                if connection.execute(
                    "SELECT 1 FROM combined WHERE batch=?", (batch["id"],)
                ).fetchone():
                    continue
                rows = [
                    row
                    for artifact in batch["result"]["artifacts"]
                    for row in artifact["data"].get("rows", [])
                    if "term" in row and "count" in row
                ]
                with self.guard(), connection:
                    connection.executemany(
                        "INSERT INTO terms VALUES(?,?,?)",
                        [(batch["id"], row["term"], row["count"]) for row in rows],
                    )
                    connection.execute("INSERT INTO combined VALUES(?)", (batch["id"],))
            top_k = max(1, int(header["config"].get("top_k", 20)))
            minimum = max(1, int(header["config"].get("min_count", 1)))
            rows = [
                {"term": term, "count": frequency}
                for term, frequency in connection.execute(
                    "SELECT term,SUM(frequency) AS total FROM terms GROUP BY term HAVING total>=? ORDER BY total DESC,term LIMIT ?",
                    (minimum, top_k),
                )
            ]
        return {
            "artifact_type": "table",
            "title": "Keyword frequencies",
            "description": "Counts combined across every saved-text batch before ranking.",
            "columns": [
                {"key": "term", "label": "Term", "data_type": "string"},
                {"key": "count", "label": "Count", "data_type": "integer"},
            ],
            "rows": rows,
            "keywords": rows,
        }

    def finish(self, final):
        from osii.domain.artifacts.enrichment_artifacts import _scope_enrichment_dir
        from osii.domain.artifacts.products import product_provenance, write_artifact

        header = self.header()
        progress = self.summary()
        if progress["processed_characters"] != progress["text_characters"]:
            raise ValueError("Not every saved-text character has completed its batch")
        outputs = publication_outputs(
            self.run_id,
            progress,
            header["title"],
            final,
            next(self.rows("map", 0))["result"],
        )
        if header["processor"] == "stats_keywords":
            keywords = self.keyword_result(header)
            if keywords is None:
                return False
            outputs = [
                row for row in outputs if row["id"] != "keywords--stats_keywords"
            ]
            outputs.append(
                {
                    "id": "keywords--stats_keywords",
                    "family": "enrichment",
                    "data": keywords,
                }
            )
        directory = _scope_enrichment_dir(self.root, header["scope"])[1]
        from osii.domain.processing.scope_batches import sampled_keywords

        samples = sampled_keywords(self.rows("map", 0))
        for output in outputs:
            if output["data"].get("artifact_type") == "scope_batch_run":
                output["data"]["keyword_samples"] = samples
        provenance = {
            "run_id": self.run_id,
            "batch_run_id": self.run_id,
            "scope": header["scope"],
            "member_ids": header["member_ids"],
            "inputs": header["source_inputs"],
            "input_summary": progress,
            "tool": header["processor"],
        }
        from osii.domain.artifacts.products import product_input_state
        from osii.domain.storage.commits import CommitConflict

        with self.guard(), product_provenance(provenance):
            if (
                product_input_state(
                    self.root,
                    header["scope"],
                    {
                        "current": "frozen",
                        "revisions": [{"id": "frozen", "provenance": provenance}],
                    },
                )
                != "current"
            ):
                raise CommitConflict(
                    "Scope input text or membership changed; stage a new processing step"
                )
            for output in outputs:
                name = (
                    f"{output['id']}--{header['processor']}.json"
                    if output["id"] in {"batch-results", "wiki"}
                    else output["id"] + ".json"
                )
                write_artifact(self.root, directory / name, output["data"])
        run = get_run(self.run_id)
        run["items"][0].update(status="done", finished_at=datetime.now(UTC).isoformat())
        run.update(
            completed=1,
            status="done",
            finished_at=datetime.now(UTC).isoformat(),
            error=None,
        )
        save_run(run)


def submit(root, payload):
    from osii.domain.tool_actions import (
        validate_tool_config,
        _fingerprint,
        resolve_enricher,
        resolve_tool_models,
        model_connection,
        merged_processor_settings,
    )
    from osii.domain.artifacts.products import validate_scope
    from osii.domain.artifacts.enrichment_artifacts import _scope_enrichment_dir
    from osii.expert_context import resolve_expert_context
    from osii.domain.scopes.membership import list_scope_file_ids
    from osii.domain.artifacts.text_representations import (
        get_preferred_text_representation,
    )
    from osii.domain.read.docs import get_doc_meta

    scope = validate_scope(payload.get("scope") or {})
    name = payload["enricher_name"]
    tool = resolve_enricher(name)
    descriptor = tool.describe()
    supported = descriptor.get("capabilities", {}).get("scope_types")
    if supported and scope["scope_type"] not in supported:
        raise ValueError("This method does not support the selected scope")
    config = {
        **{
            key: value["default"]
            for key, value in descriptor.get("config_schema", {})
            .get("properties", {})
            .items()
            if "default" in value
        },
        **merged_processor_settings(root, name, payload.get("enricher_config")),
    }
    validate_tool_config(descriptor.get("config_schema") or {}, config)
    bindings = resolve_tool_models(
        name,
        descriptor.get("model_requirements") or {},
        root,
        payload.get("model_bindings") or {},
    )
    members = sorted(set(list_scope_file_ids(root, scope)))
    if not members:
        raise ValueError("No documents are in this scope")
    scope_path = _scope_enrichment_dir(root, scope)[1]
    run = create_run_record([scope_path], root, root, osii_root=root)
    run_id = run["id"]
    storage = LocalBatchStorage(root, run_id)
    storage.directory.mkdir(parents=True, exist_ok=False)
    batch_characters = min(
        100000,
        int(config.get("max_input_chars", 100000)),
        int(config.get("window_chars", 100000)),
    )
    summary = {
        "batch_characters": batch_characters,
        "documents": len(members),
        "documents_with_text": 0,
        "documents_without_text": 0,
        "text_characters": 0,
        "map_batches": 0,
        "completed_batches": 0,
        "completed_documents": 0,
        "processed_characters": 0,
        "reduce_batches": 0,
        "reduction": descriptor.get("capabilities", {}).get(
            "batch_reduction", "partitioned"
        ),
        "phase": "map",
    }
    sources = []

    def texts():
        for fid in members:
            preferred = get_preferred_text_representation(root, fid)
            if preferred is None:
                summary["documents_without_text"] += 1
                sources.append(
                    {
                        "file_id": fid,
                        "filename": fid,
                        "has_text": False,
                        "full_chars": 0,
                        "source_sha256": None,
                    }
                )
                continue
            text = preferred.get("text") or ""
            if text.strip():
                summary["documents_with_text"] += 1
                summary["text_characters"] += len(text)
            else:
                summary["documents_without_text"] += 1
            meta = get_doc_meta(root, fid) or {}
            file = meta.get("file", {})
            row = {
                "has_text": bool(text.strip()),
                "file_id": fid,
                "text": text,
                "filename": file.get("filename") or fid,
                "media_type": file.get("mime") or "text/plain",
                "source_relpath": file.get("source_relpath"),
                "extraction_id": preferred.get("extraction_id")
                or preferred.get("name")
                or "canonical",
                "representation": preferred.get("name"),
                "path": preferred.get("path"),
                "full_chars": len(text),
                "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            sources.append({k: v for k, v in row.items() if k != "text"})
            yield row

    try:
        for index, items in enumerate(
            input_batches(texts(), BatchLimits(characters=batch_characters))
        ):
            _save(
                storage.directory / f"map-0-{index}.json",
                {
                    "id": f"map-{index}",
                    "ordinal": index,
                    "phase": "map",
                    "level": 0,
                    "inputs": items,
                    "source_ranges": coverage(items),
                    "result": None,
                    "calls": {},
                },
            )
            _save(
                storage.directory / f"info-map-{index}.json",
                {
                    "id": f"map-{index}",
                    "ordinal": index,
                    "phase": "map",
                    "level": 0,
                    "source_ranges": coverage(items),
                },
            )
            summary["map_batches"] += 1
        if not summary["map_batches"]:
            raise ValueError("Read document text before running this tool")
        context = resolve_expert_context(root, scope, payload.get("expert_context"))
        header = {
            "summary": summary,
            "levels": {"map:0": summary["map_batches"]},
            "scope": scope,
            "member_ids": members,
            "source_inputs": sources,
            "processor": name,
            "title": descriptor.get("display_name", name),
            "config": config,
            "bindings": bindings,
            "expert_context": context,
            "descriptor_fingerprint": _fingerprint(descriptor),
            "model_fingerprints": {
                cap: _fingerprint(model_connection(alias, root))
                for cap, alias in bindings.items()
            },
        }
        storage.save_header(header)
        run.update(
            status="queued",
            workflow="tool",
            tool_id=name,
            tool_label=header["title"],
            scope=scope,
            control_state="running",
            batch_progress=summary,
        )
        run["items"][0]["display"] = header["title"]
        save_run(run)
        enqueue_run(
            run_id,
            {
                "job_kind": "tool",
                "batch_version": 1,
                "osii_store": str(root),
                "processor": name,
                "scope": scope,
            },
        )
    except Exception:
        run.update(
            status="error",
            error="Scope input preparation failed; no processor was invoked",
        )
        save_run(run)
        raise
    return {
        "run_id": run_id,
        "status": "queued",
        "scope": scope,
        "enricher_name": name,
        "input_summary": summary,
    }


def _execute(job):
    from osii.domain.tool_actions import (
        _BINDINGS,
        _fingerprint,
        resolve_enricher,
        model_connection,
    )
    from osii.enrichment.common import frozen_scope_inputs
    from osii.domain.artifacts.enrichment_artifacts import capture_batch_outputs
    from osii.processor_sdk import ProcessorClient, EnrichmentRequest

    root = Path(job["payload"]["osii_store"])
    run_id = job["run_id"]
    if (get_run(run_id) or {}).get("status") == "done":
        return
    storage = LocalBatchStorage(root, run_id, job)
    header = storage.header()
    tool = resolve_enricher(header["processor"])
    if _fingerprint(tool.describe()) != header["descriptor_fingerprint"]:
        raise ValueError("The selected tool changed; start a new run")
    for cap, alias in header["bindings"].items():
        if (
            _fingerprint(model_connection(alias, root))
            != header["model_fingerprints"][cap]
        ):
            raise ValueError(
                "The selected model changed since submission; restore it to resume this run"
            )

    def ready():
        return not honor_run_control(run_id)

    def call(row):
        run = get_run(run_id)
        run.update(
            status="running",
            started_at=run.get("started_at") or datetime.now(UTC).isoformat(),
        )
        run["items"][0]["status"] = "running"
        save_run(run)
        token = _BINDINGS.set(
            (header["processor"], header["bindings"], header["expert_context"])
        )
        try:
            if hasattr(tool, "base_url"):
                from osii.processors.remote import _model_context, _revoke_model_context

                request = EnrichmentRequest(
                    request_id=f"{run_id}:{row['id']}",
                    scope=request_scope(
                        header["scope"],
                        row["inputs"],
                        phase=row["phase"],
                        batch_id=row["id"],
                    ),
                    config=header["config"],
                    expert_context=(
                        (
                            "Combine these derived summaries; they are not original evidence. Preserve uncertainty and original source identifiers.\n"
                            if row["phase"] == "reduce"
                            else ""
                        )
                        + (header["expert_context"] or "")
                    )
                    or None,
                )
                context = _model_context(
                    processor_name=header["processor"],
                    descriptor=tool.describe(),
                    request_id=request.request_id,
                    osii_root=root,
                )
                try:
                    request.model_context = context
                    response = ProcessorClient(tool.base_url).enrich(request)
                    if (
                        response.request_id != request.request_id
                        or response.processor.name != header["processor"]
                        or response.processor.version != tool.describe()["version"]
                    ):
                        raise ValueError("Processor returned a mismatched batch result")
                    if len(response.model_dump_json()) > 4_000_000:
                        raise ValueError(
                            "Batch output exceeds 4 MiB; use shorter processor output"
                        )
                    return response
                finally:
                    _revoke_model_context(context)
            with (
                frozen_scope_inputs(root, header["scope"], row["inputs"]),
                capture_batch_outputs() as outputs,
            ):
                result = tool.enrich(
                    osii_store=root,
                    scope=header["scope"],
                    expert_context=header["expert_context"],
                    enricher_config={
                        **header["config"],
                        **(
                            {"top_k": 100000, "min_count": 1}
                            if header["processor"] == "stats_keywords"
                            else {}
                        ),
                    },
                )
                if result.get("ok") is False:
                    raise ValueError("Tool did not produce a batch result")
                if (
                    not outputs
                    and isinstance(result.get("result"), dict)
                    and isinstance(result["result"].get("text"), str)
                ):
                    outputs.append(
                        {
                            "id": "result",
                            "data": {
                                "artifact_type": "text",
                                "title": header["title"],
                                "text": result["result"]["text"],
                            },
                        }
                    )
                if not outputs:
                    raise ValueError("Tool did not produce a batch result")
                return {"artifacts": outputs}
        finally:
            _BINDINGS.reset(token)

    try:
        execute_batches(storage, call, ready, lambda line: append_log(run_id, line))
    except Exception as exc:
        run = get_run(run_id)
        run.update(status="error", error=str(exc), error_phase="tool")
        run["items"][0].update(status="error", error=str(exc))
        save_run(run)
        raise


def details(root, run_id, cursor=0, limit=20):
    if cursor < 0 or not 1 <= limit <= 50:
        raise ValueError("Invalid batch page")
    storage = LocalBatchStorage(root, run_id)
    total = storage.summary()["map_batches"]
    items = []
    for index in range(cursor, min(cursor + limit, total)):
        row = _read(storage.directory / f"info-map-{index}.json")
        row["status"] = (
            "done"
            if (storage.directory / f"result-map-{index}.json").is_file()
            else "pending"
        )
        items.append(row)
    return {
        "items": items,
        "next_cursor": cursor + limit if cursor + limit < total else None,
    }


def batch_result(root, run_id, batch_id):
    import re

    if not re.fullmatch(r"(map-\d+|reduce-\d+-\d+)", batch_id):
        raise ValueError("Invalid batch identifier")
    storage = LocalBatchStorage(root, run_id)
    path = storage._path(batch_id)
    row = _read(path)
    result_path = storage.directory / f"result-{batch_id}.json"
    return {
        "id": batch_id,
        "source_ranges": row["source_ranges"],
        "result": _read(result_path) if result_path.is_file() else None,
    }


def execute(job):
    try:
        return _execute(job)
    except Exception as exc:
        run = get_run(job["run_id"])
        if run:
            run.update(status="error", error=str(exc), error_phase="tool")
            run["items"][0].update(status="error", error=str(exc))
            save_run(run)
        raise


def source_details(root, run_id, cursor=0, limit=50, only_missing=False):
    if cursor < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid source page")
    rows = LocalBatchStorage(root, run_id).header()["source_inputs"]
    if only_missing:
        rows = [row for row in rows if not row.get("has_text")]
    return {
        "items": rows[cursor : cursor + limit],
        "next_cursor": cursor + limit if cursor + limit < len(rows) else None,
    }
