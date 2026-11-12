"""Compatibility operations over the same durable scope queue as other tools."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from osii.configuration import load_models_config
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.read.synthesis import get_synth_text
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.storage.objects import object_text_path
from osii.synthesis.common import read_concatenated_text
from osii.synthesis.registry import resolve_synthesis_method


def synthesis_inputs(root: Path, scope: dict) -> dict:
    """Retain full compatibility inputs on local disk, never in a provider request."""
    members = sorted(set(list_scope_file_ids(root, scope)))
    documents = []
    for file_id in members:
        if scope["scope_type"] == "collection":
            path = object_text_path(root, file_id)
            text = get_synth_text(root, file_id) or (
                path.read_text(encoding="utf-8") if path.exists() else ""
            )
            row = {"file_id": file_id, "text": text}
        else:
            preferred = get_preferred_text_representation(root, file_id)
            native, count = read_concatenated_text(root, file_id)
            row = {
                **(preferred or {}),
                "file_id": file_id,
                "text": (preferred or {}).get("text") or native,
                "native_text": native,
                "text_record_count": count,
            }
        if "native_text" in row:
            row["native_source_sha256"] = hashlib.sha256(
                row["native_text"].encode()
            ).hexdigest()
            if row["native_text"] == row["text"]:
                row.pop("native_text")
        row["source_sha256"] = hashlib.sha256(row["text"].encode()).hexdigest()
        documents.append(row)
    return {
        "documents": documents,
        "member_ids": members,
        "text_chars": sum(len(item["text"]) for item in documents),
        "truncated_documents": 0,
    }


class SynthesisAction:
    """Adapt existing synthesis methods to the shared scope-tool lifecycle."""

    def __init__(self, root: Path, name: str, scope: dict):
        self.root, self.name, self.scope = root, name, scope
        if scope["scope_type"] == "collection":
            if name != "collection_firstn":
                raise ValueError(f"Unsupported collection synthesizer: {name}")
            from osii.synthesis.collection.firstn import CollectionFirstNSynthesizer

            self.methods = [CollectionFirstNSynthesizer()]
        else:
            names = list(
                dict.fromkeys(
                    [
                        name,
                        *[
                            n.strip()
                            for n in os.getenv("OSII_SYNTHESIZER_FALLBACKS", "").split(
                                ","
                            )
                            if n.strip()
                        ],
                    ]
                )
            )
            self.methods = [resolve_synthesis_method(name)]
            self.fallback_names = names[1:]

    def describe(self):
        descriptors = [method.describe() for method in self.methods]
        configuration = {
            "models": load_models_config(self.root),
            "environment": {
                key: os.getenv(key, "")
                for key in (
                    "OSII_CHAT_BASE_URL",
                    "OSII_MODEL_BASE_URL",
                    "OPENAI_BASE_URL",
                    "OLLAMA_BASE_URL",
                    "OLLAMA_CHAT_MODEL",
                    "OLLAMA_SYNTHESIS_MODEL",
                )
            },
        }
        if self.name in {"firstN", "collection_firstn"}:
            configuration = {}  # These methods do not consume a model.
        return {
            **descriptors[0],
            "fallbacks": getattr(self, "fallback_names", []),
            "model_configuration_fingerprint": hashlib.sha256(
                json.dumps(configuration, sort_keys=True).encode()
            ).hexdigest(),
        }

    def enrich(self, *, osii_store, scope, expert_context=None, enricher_config=None):
        failures = []
        for name in [self.name, *getattr(self, "fallback_names", [])]:
            try:
                method = (
                    self.methods[0]
                    if name == self.name
                    else resolve_synthesis_method(name)
                )
                arguments = {
                    "osii_store": osii_store,
                    "expert_context": expert_context,
                    "synthesizer_config": enricher_config or {},
                }
                if scope["scope_type"] == "collection":
                    result = method.synthesize_collection(
                        collection_id=scope["collection_id"], **arguments
                    )
                    saved = result
                else:
                    result = method.synthesize(file_id=scope["file_id"], **arguments)
                    saved = result.get("synthesis_rel") or result.get("synth_rel")
                if result.get("error"):
                    raise RuntimeError(result["error"])
                return {"ok": True, "result": saved, **({"fallback_failures": list(failures), "actual_synthesizer": name} if failures else {})}
            except Exception as exc:
                failures.append(f"{name}: {exc}")
        raise RuntimeError("All synthesis providers failed: " + "; ".join(failures))


def embedding_binding(root: Path) -> dict:
    from osii.configuration import model_connection
    from osii.domain.model_provider_config import selected_model, selected_processor

    configuration = load_models_config(root)
    alias = configuration.get("defaults", {}).get("embedding")
    connection = model_connection(alias, root) if alias else {}
    return {
        "model": selected_model("embedder", osii_root=root),
        "processor": selected_processor("embedder", osii_root=root),
        "connection": {
            key: (connection or {}).get(key)
            for key in ("type", "base_url", "model", "capabilities", "enabled")
        },
        "direct_url": os.getenv("OSII_EMBEDDING_BASE_URL")
        or os.getenv("OSII_MODEL_BASE_URL")
        or os.getenv("OPENAI_BASE_URL", ""),
    }


def validate_embedding_binding(root: Path, payload: dict):
    if embedding_binding(root) != payload["embedding_binding"]:
        raise ValueError(
            "This run's embedding connection changed. Restore it before retrying, or start a new rebuild."
        )


def submit_full_index(
    root: Path,
    *,
    batch_size: int,
    chunking_method: str,
    chunk_size: int,
    chunk_overlap: int,
) -> dict:
    from osii.domain.processing.jobs import create_run_record, save_run, enqueue_run
    from osii.domain.read.catalog import load_files_catalog

    members = sorted({item["file_id"] for item in load_files_catalog(root)})
    binding = embedding_binding(root)
    run = create_run_record(
        [root / "objects" / file_id for file_id in members], root, root, osii_root=root
    )
    for item, file_id in zip(run["items"], members):
        item["file_id"] = file_id
    run.update(
        status="queued",
        control_state="running",
        workflow="library",
        tool_label="Full index rebuild",
        file_processing_status="done",
        indexing_status="queued",
        indexing_file_ids=members,
        operations={"extract": False, "embed": True},
        input_revision_policy="current-text-on-retry",
    )
    save_run(run)
    enqueue_run(
        run["id"],
        {
            "job_kind": "full_index",
            "osii_store": str(root),
            "build_embeddings": True,
            "embedding_model": binding["model"],
            "embedding_binding": binding,
            "document_paths": [str(root / "objects" / file_id) for file_id in members],
            "embedding_batch_size": batch_size,
            "chunking_method": chunking_method,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        alias="embeddings:segments",
    )
    return run
