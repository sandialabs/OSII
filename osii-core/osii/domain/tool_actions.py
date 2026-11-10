"""Capability catalog and durable, bounded tool execution owned by Core."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from osii.expert_context import frozen_scope_context
from osii.configuration import load_models_config, model_connection, resolve_tool_models
from osii.domain.artifacts.products import product_provenance, validate_scope
from osii.domain.processing.jobs import (
    append_log,
    create_run_record,
    enqueue_run,
    get_run,
    save_run,
)
from osii.domain.processor_settings import merged_processor_settings
from osii.domain.storage.atomic import atomic_write_text
from osii.enrichment.common import frozen_scope_inputs, snapshot_scope
from osii.enrichment.registry import get_enrichers, resolve_enricher

_BINDINGS = ContextVar("tool_model_bindings", default=None)


def frozen_bindings(processor: str) -> dict | None:
    value = _BINDINGS.get()
    return value[1] if value and value[0] == processor else None


def frozen_expert_context(processor: str) -> tuple[bool, str | None]:
    value = _BINDINGS.get()
    return (True, value[2]) if value and value[0] == processor else (False, None)


def _fingerprint(value: dict | None) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def model_choices(root: Path) -> dict:
    configuration = load_models_config(root)
    models = [
        {
            "id": name,
            "label": f"{connection.get('model') or name} · {name}",
            "capabilities": connection.get("capabilities", []),
        }
        for name in configuration.get("models", {})
        if (connection := model_connection(name, root))
    ]
    return {"models": models, "defaults": configuration.get("defaults", {})}


def tool_catalog(root: Path) -> dict:
    methods = []
    for enricher in get_enrichers():
        descriptor = enricher.describe()
        outputs = descriptor.get("capabilities", {}).get("output_kinds", [])
        actions = {
            "wiki_markdown": "wiki.write",
            "document_metadata": "metadata.suggest",
            "topics": "topics.model",
            "recommendations": "documents.recommend",
            "embedding_projection": "topics.project",
        }
        action = next((actions[kind] for kind in outputs if kind in actions), "analyze")
        try:
            bindings = resolve_tool_models(
                enricher.name, descriptor.get("model_requirements") or {}, root
            )
            error = None
        except ValueError as exc:
            bindings, error = {}, str(exc)
        methods.append(
            {
                "id": enricher.name,
                "action": action,
                "label": descriptor.get("display_name", enricher.name),
                "version": descriptor.get("version"),
                "scopes": descriptor.get("capabilities", {}).get("scope_types")
                or ["object", "folder", "collection", "root"],
                "inputs": ["text"],
                "outputs": outputs,
                "config_schema": descriptor.get("config_schema") or {},
                "model_requirements": descriptor.get("model_requirements") or {},
                "bindings": bindings,
                "configuration_error": error,
                "limits": {"documents": 1000, "characters": 200000},
                "execution": "scope",
                "resume": "frozen-inputs",
            }
        )
    from osii.extraction.registry import get_extractors
    from osii.synthesis.registry import get_synthesizers
    from osii.processors.remote import discover_remote_processors

    descriptors = [("extractor", item.describe()) for item in get_extractors()]
    descriptors += [("synthesizer", item.describe()) for item in get_synthesizers()]
    descriptors += [
        (item["kind"], item)
        for item in discover_remote_processors()
        if item.get("kind") != "enricher"
    ]
    for kind, descriptor in descriptors:
        identity = descriptor.get("name")
        if not identity or any(item["id"] == identity for item in methods):
            continue
        methods.append(
            {
                "id": identity,
                "label": descriptor.get("display_name", identity),
                "version": descriptor.get("version"),
                "action": {
                    "extractor": "text.read",
                    "synthesizer": "summary.write",
                    "embedder": "embedding.build",
                }.get(kind, "analyze"),
                "scopes": descriptor.get("capabilities", {}).get("scope_types")
                or ["object"],
                "inputs": ["source" if kind == "extractor" else "text"],
                "outputs": descriptor.get("capabilities", {}).get("output_kinds") or [],
                "config_schema": descriptor.get("config_schema") or {},
                "model_requirements": descriptor.get("model_requirements") or {},
                "bindings": {},
                "configuration_error": None,
                "execution": "intake",
                "resume": "per-document",
                "limits": {"documents": 10000, "characters": 0},
            }
        )
    return {
        "library_id": hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20],
        "methods": methods,
        **model_choices(root),
    }


def resolve_scope_method(root: Path, processor: str, scope: dict, method_kind: str):
    if method_kind == "synthesis":
        from osii.domain.processing.standalone import SynthesisAction

        return SynthesisAction(root, processor, scope)
    if method_kind != "enricher":
        raise ValueError("Unsupported scope operation")
    return resolve_enricher(processor)


def submit_tool(root: Path, payload: dict, *, method_kind: str = "enricher") -> dict:
    processor = str(payload.get("enricher_name") or "").strip()
    if not processor:
        raise ValueError("Choose a tool method.")
    scope = validate_scope(payload.get("scope") or {})
    enricher = resolve_scope_method(root, processor, scope, method_kind)
    descriptor = enricher.describe()
    scopes = descriptor.get("capabilities", {}).get("scope_types")
    if scopes and scope["scope_type"] not in scopes:
        raise ValueError("This method does not support the selected scope.")
    bindings = resolve_tool_models(
        processor,
        descriptor.get("model_requirements") or {},
        root,
        payload.get("model_bindings") or {},
    )
    targets = {
        cap: {
            "alias": alias,
            "model": (model_connection(alias, root) or {}).get("model"),
            "endpoint_type": (model_connection(alias, root) or {}).get("type"),
        }
        for cap, alias in bindings.items()
    }
    if method_kind == "synthesis":
        from osii.domain.processing.standalone import synthesis_inputs

        snapshot = synthesis_inputs(root, scope)
    else:
        snapshot = snapshot_scope(root, scope)
    config = merged_processor_settings(root, processor, payload.get("enricher_config"))
    validate_tool_config(descriptor.get("config_schema") or {}, config)
    # Freeze expert context at submission, too; retry must not pick up a changed scope note.
    from osii.expert_context import resolve_expert_context

    expert_context = resolve_expert_context(root, scope, payload.get("expert_context"))
    from osii.domain.artifacts.enrichment_artifacts import _scope_enrichment_dir

    scope_directory = _scope_enrichment_dir(root, scope)[1]
    scope_path = (
        scope_directory if scope["scope_type"] == "folder" else scope_directory.parent
    )
    run = create_run_record([scope_path], root, root, osii_root=root)
    run.update(
        status="queued",
        workflow="tool",
        tool_id=processor,
        tool_label=descriptor.get("display_name", processor),
        scope=scope,
        model_bindings=bindings,
        model_targets=targets,
        input_summary={k: v for k, v in snapshot.items() if k != "documents"},
        control_state="running",
    )
    run["items"][0]["display"] = run["tool_label"]
    if method_kind == "synthesis":
        input_path = root / "state" / "job-inputs" / f"{run['id']}.json"
        atomic_write_text(input_path, json.dumps(snapshot))
        queued_snapshot = {"path": str(input_path.relative_to(root))}
    else:
        queued_snapshot = snapshot
    save_run(run)
    enqueue_run(
        run["id"],
        {
            "job_kind": "tool",
            "osii_store": str(root),
            "processor": processor,
            "method_kind": method_kind,
            "descriptor_version": descriptor.get("version"),
            "descriptor_fingerprint": _fingerprint(descriptor),
            "scope": scope,
            "scope_path": str(scope_path),
            "document_paths": [
                str(root / "objects" / file_id) for file_id in snapshot["member_ids"]
            ],
            "snapshot": queued_snapshot,
            "config": config,
            "expert_context": expert_context,
            "bindings": bindings,
            "model_targets": targets,
            "model_fingerprints": {
                cap: _fingerprint(model_connection(alias, root))
                for cap, alias in bindings.items()
            },
        },
    )
    return {
        "run_id": run["id"],
        "status": "queued",
        "scope": scope,
        "enricher_name": processor,
        "model_bindings": bindings,
        "input_summary": run["input_summary"],
    }


def execute_tool(job: dict):
    payload = job["payload"]
    root, run_id = Path(payload["osii_store"]), job["run_id"]
    run = get_run(run_id)
    if not run or run.get("control_state") in {
        "pause_requested",
        "cancel_requested",
        "paused",
        "cancelled",
    }:
        return
    marker = root / "state" / "tool-results" / f"{run_id}.json"
    try:
        if marker.is_file():
            result = json.loads(marker.read_text(encoding="utf-8"))
        else:
            enricher = resolve_scope_method(
                root,
                payload["processor"],
                payload["scope"],
                payload.get("method_kind", "enricher"),
            )
            snapshot = payload["snapshot"]
            if "path" in snapshot:
                snapshot = json.loads(
                    (root / snapshot["path"]).read_text(encoding="utf-8")
                )
            if _fingerprint(enricher.describe()) != payload.get(
                "descriptor_fingerprint"
            ):
                raise ValueError(
                    "This tool changed since submission. Start a new run to use the new version."
                )
            for cap, alias in payload["bindings"].items():
                if (
                    _fingerprint(model_connection(alias, root))
                    != payload["model_fingerprints"][cap]
                ):
                    raise ValueError(
                        "The selected model changed since submission. Start a new run to use it."
                    )
            run.update(
                status="running",
                started_at=run.get("started_at") or datetime.now(UTC).isoformat(),
            )
            run["items"][0]["status"] = "running"
            save_run(run)
            append_log(run_id, "Running tool on saved text inputs.")
            provenance = {
                "run_id": run_id,
                "tool": payload["processor"],
                "version": payload.get("descriptor_version"),
                "scope": payload["scope"],
                "models": payload.get("model_targets", payload["bindings"]),
                "member_ids": snapshot["member_ids"],
                **({"processing_revision": snapshot["processing_revision"]} if "processing_revision" in snapshot else {}),
                "inputs": [
                    {k: v for k, v in doc.items() if k not in {"text", "native_text"}}
                    for doc in snapshot["documents"]
                ],
            }
            token = _BINDINGS.set(
                (
                    payload["processor"],
                    payload["bindings"],
                    payload.get("expert_context"),
                )
            )
            try:
                with (
                    frozen_scope_inputs(root, payload["scope"], snapshot["documents"]),
                    product_provenance(provenance),
                    frozen_scope_context(
                        root, payload["scope"], payload.get("expert_context")
                    ),
                ):
                    result = enricher.enrich(
                        osii_store=root,
                        scope=payload["scope"],
                        expert_context=payload.get("expert_context"),
                        enricher_config=payload["config"],
                    )
            finally:
                _BINDINGS.reset(token)
            if result.get("ok") is False:
                raise RuntimeError(result.get("error") or "Tool did not save a result")
            if result.get("fallback_failures"):
                append_log(run_id, f"Synthesis used fallback {result['actual_synthesizer']}; earlier failures: {'; '.join(result['fallback_failures'])}")
            atomic_write_text(marker, json.dumps(result))
        # Respect controls received while a provider request was in flight. The
        # saved result is reused on resume; it is never generated again.
        run = get_run(run_id)
        run["items"][0].update(
            status="done", enrichment=result.get("result"), error=None
        )
        if payload.get("method_kind") == "synthesis":
            run["items"][0]["synthesis"] = result.get("result")
            if payload["scope"]["scope_type"] == "object":
                run["items"][0]["file_id"] = payload["scope"]["file_id"]
        run["completed"] = 1
        if run.get("control_state") not in {"pause_requested", "cancel_requested"}:
            run.update(
                status="done", error=None, finished_at=datetime.now(UTC).isoformat()
            )
        save_run(run)
        append_log(run_id, "Results saved.")
    except Exception as exc:
        run = get_run(run_id)
        if run:
            run.update(
                status="error",
                error=str(exc),
                error_phase="tool",
                finished_at=datetime.now(UTC).isoformat(),
            )
            run["items"][0].update(status="error", error=str(exc))
            save_run(run)
            append_log(run_id, f"Tool failed: {exc}")
        raise


def validate_tool_config(schema: dict, config: dict):
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in config and "default" not in properties.get(name, {}):
            raise ValueError(f"Set {name.replace('_', ' ')} in Options.")
    for name, value in config.items():
        prop = properties.get(name)
        if prop is None:
            if schema.get("additionalProperties") is False:
                raise ValueError(f"Unknown option: {name}")
            continue
        kind = prop.get("type")
        valid = {
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "string": isinstance(value, str),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }
        if kind in valid and not valid[kind]:
            raise ValueError(f"Invalid value for {name.replace('_', ' ')}")
        if prop.get("enum") and value not in prop["enum"]:
            raise ValueError(f"Choose an available {name.replace('_', ' ')}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if ("minimum" in prop and value < prop["minimum"]) or (
                "maximum" in prop and value > prop["maximum"]
            ):
                raise ValueError(
                    f"{name.replace('_', ' ')} is outside its allowed range"
                )
