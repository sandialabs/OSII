"""Core-owned sidecar commits over existing extraction and product formats."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
import base64
import json
import mimetypes
import os
from pathlib import Path
import tempfile

import tomli_w

from osii.domain.read.sidecar import SidecarLibraryReader
from osii.domain.storage.atomic import atomic_write_text
from osii.domain.storage.commits import CommitConflict, CommitReceipt, JobCheckpoint, ProcessingCommit, embedding_identity
from osii.processor_sdk import EmbeddingResponse, EnrichmentResponse, ExtractionResponse, SynthesisResponse


def _toml_value(value):
    if isinstance(value, dict):
        return {key: _toml_value(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_toml_value(item) for item in value if item is not None]
    return value


@contextmanager
def _lock(root: Path):
    path = root / "state" / "processing-commits.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class SidecarProcessingCommitter:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.reader = SidecarLibraryReader(self.root)

    def commit(self, command: ProcessingCommit, *, checkpoint: JobCheckpoint | None = None) -> CommitReceipt:
        command.validate()
        if checkpoint is not None:
            raise ValueError("Local queue checkpoints remain owned by the local job store")
        fingerprint = command.fingerprint()
        receipt_path = self.root / "runs" / f"commit-{command.commit_id}.json"
        with _lock(self.root):
            if receipt_path.is_file():
                saved = json.loads(receipt_path.read_text(encoding="utf-8"))
                if saved["fingerprint"] != fingerprint:
                    raise CommitConflict("Operation ID was already used for a different result")
                return replace(CommitReceipt(**saved["receipt"]), replayed=True)
            if command.input_revision:
                command.input_revision.verify(self.reader)
            if isinstance(command.response, ExtractionResponse):
                previous = self.reader.get_document(command.file_id)
                if previous and previous.sha256 and previous.sha256 != command.source.sha256:
                    raise CommitConflict("Document ID already belongs to different source bytes")
                result = self._extract(command)
            elif isinstance(command.response, EmbeddingResponse):
                result = self._embed(command)
            else:
                result = self._product(command)
            receipt = CommitReceipt(command.commit_id, command.file_id, command.kind, result)
            atomic_write_text(receipt_path, json.dumps({"fingerprint": fingerprint,
                "receipt": asdict(receipt)}, ensure_ascii=False))
            return receipt

    def _extract(self, command: ProcessingCommit) -> dict:
        from osii.domain.artifacts.extraction_variants import (_archive_legacy_primary,
            _load_index, _variant_record, _write_index,
            promote_extraction_variant)
        source, response = command.source, command.response
        obj = self.root / "objects" / command.file_id
        target = obj / "extractions" / command.commit_id
        # A deterministic immutable bundle makes retry safe even if registration
        # or compatibility promotion was interrupted before the receipt existed.
        if target.is_dir():
            saved = json.loads((target / "commit.json").read_text(encoding="utf-8"))
            if saved["fingerprint"] != command.fingerprint():
                raise CommitConflict("Extraction commit already contains a different result")
            if saved.get("result"):
                return saved["result"]
        else:
            obj.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".processing-", dir=obj.parent) as temporary:
                stage = Path(temporary)
                parts, records, position = [], [], 0
                for index, segment in enumerate(response.segments, 1):
                    if parts:
                        parts.append(command.text_separator)
                        position += len(command.text_separator)
                    start = position
                    parts.append(segment.text)
                    position += len(segment.text)
                    records.append({"id": f"seg-{index:06d}", "kind": "text", "type": segment.segment_type,
                        "path": "text.txt", "span": {"char_start": start, "char_end": position},
                        "source_origin": {**segment.source_origin, "processor_segment_id": segment.id},
                        **({"related_ids": segment.related_ids} if segment.related_ids else {})})
                (stage / "text.txt").write_text("".join(parts), encoding="utf-8")
                (stage / "artifacts").mkdir()
                for index, artifact in enumerate(response.artifacts, 1):
                    extension = mimetypes.guess_extension(artifact.media_type) or ".bin"
                    name = f"artifacts/artifact-{index:06d}{extension}"
                    data = artifact.data_base64
                    if data is not None:
                        content = base64.b64decode(data, validate=True)
                    elif artifact.text is not None:
                        content = artifact.text.encode("utf-8")
                    else:
                        payload = artifact.json_data if artifact.json_data is not None else artifact.standard_data.model_dump(mode="json")
                        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    (stage / name).write_bytes(content)
                    records.append({"id": artifact.id, "kind": artifact.kind, "type": artifact.media_type,
                        "path": name, "source_origin": artifact.source_origin})
                (stage / "manifest.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n", encoding="utf-8")
                provenance = {"provenance": {"status": "done", "pipeline_version": "osii-v1-draft", "generated_utc": datetime.now(UTC).isoformat()},
                    "extractor": {"name": response.processor.name, "version": response.processor.version},
                    "config": {**command.request.config, **command.provenance, "commit_id": command.commit_id,
                               "expert_context": command.request.expert_context, "expert_context_supplied": bool(command.request.expert_context)},
                    "counts": {"segments_written": len(response.segments), "artifacts_written": len(response.artifacts),
                               "units_attempted": len(response.segments), "units_completed": len(response.segments)},
                    "response_metadata": response.document_metadata,
                    "errors": {"warnings": response.warnings}}
                (stage / "provenance.toml").write_text(tomli_w.dumps(_toml_value(provenance)), encoding="utf-8")
                (stage / "response.json").write_text(response.model_dump_json(), encoding="utf-8")
                if command.request.expert_context:
                    (stage / "expert-context.md").write_text(command.request.expert_context, encoding="utf-8")
                (stage / "commit.json").write_text(json.dumps({"fingerprint": command.fingerprint()}), encoding="utf-8")
                # Finish all validation/staging before changing an existing bundle.
                _archive_legacy_primary(self.root, command.file_id)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, target)
        meta = {"file": {"source_relpath": source.source_relpath, "filename": source.filename,
                         "mime": source.media_type, "size_bytes": source.size_bytes,
                         **{key: source.metadata[key] for key in ("mtime_utc", "birthtime_utc") if source.metadata.get(key)}},
                "hash": {"sha256": source.sha256}, "meta": source.metadata}
        atomic_write_text(obj / "meta.toml", tomli_w.dumps(_toml_value(meta)))
        index = _load_index(self.root, command.file_id)
        record = next((row for row in index["variants"] if row["id"] == command.commit_id), None)
        if record is None:
            record = _variant_record(target, command.commit_id)
            index["variants"].append(record)
            _write_index(self.root, command.file_id, index)
        primary = command.make_primary or not index.get("primary_id")
        if primary:
            promote_extraction_variant(self.root, command.file_id, command.commit_id)
        result = {"variant_id": command.commit_id, "made_primary": primary, "extraction": record}
        atomic_write_text(target / "commit.json", json.dumps({"fingerprint": command.fingerprint(), "result": result}))
        return result

    def _embed(self, command: ProcessingCommit) -> dict:
        response = command.response
        identity = embedding_identity(response)
        path = self.root / "embeddings" / "processor-results" / f"{command.commit_id}.json"
        payload = {"response": response.model_dump(mode="json"), "input": asdict(command.input_revision),
                   "identity": identity, "commit_id": command.commit_id, "fingerprint": command.fingerprint()}
        if path.is_file() and json.loads(path.read_text(encoding="utf-8")) != payload:
            raise CommitConflict("Embedding commit already contains a different result")
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False))
        # Publishing a complete FAISS generation remains the indexer's job.
        return {"path": path.relative_to(self.root).as_posix(), "identity": identity}

    def _product(self, command: ProcessingCommit) -> dict:
        from osii.domain.artifacts.products import product_provenance
        from osii.domain.artifacts.artifact_staleness import clear_artifacts_stale
        from osii.domain.storage.objects import update_synthesis_provenance
        from osii.domain.artifacts.products import publish_product
        response = command.response
        provenance = {**command.provenance, "commit_id": command.commit_id,
            "commit_fingerprint": command.fingerprint(),
            "input_extraction_id": command.input_revision.representation_id,
            "input_text_sha256": command.input_revision.text_sha256,
            "processor": response.processor.model_dump(mode="json"), "config": command.request.config,
            "expert_context": command.request.expert_context}
        with product_provenance(provenance):
            if isinstance(response, SynthesisResponse):
                path = self.root / "objects" / command.file_id / "synth.txt"
                publish_product(self.root, path, {"artifact_type": "text", "title": "Summary", "text": response.markdown})
                config = {**command.request.config, **command.provenance, **response.metadata,
                    "input_extraction_id": command.input_revision.representation_id,
                    "input_text_sha256": command.input_revision.text_sha256,
                    "expert_context": command.request.expert_context,
                    "citations": [row.model_dump(mode="json", exclude_none=True) for row in response.citations]}
                update_synthesis_provenance(self.root, command.file_id,
                    synthesizer_name=response.processor.name, synthesizer_version=response.processor.version,
                    config=_toml_value(config), expert_context_used=bool(command.request.expert_context))
                clear_artifacts_stale(self.root, command.file_id, "syntheses")
                return {"synthesis_rel": path.relative_to(self.root).as_posix(),
                        "provenance_rel": f"objects/{command.file_id}/provenance.toml"}
            # Existing per-product manifests are commit points. If a multi-product
            # response is interrupted, completed products remain valid and retry
            # repairs the remaining products before the step receipt is written.
            from collections import Counter
            counts = Counter(item.kind for item in response.artifacts)
            results = []
            for artifact in response.artifacts:
                kind = artifact.kind.replace(" ", "_")
                method = response.processor.name if counts[artifact.kind] == 1 else f"{response.processor.name}.{artifact.id}"
                if any(char in kind + method for char in "/\\\0") or ".." in {kind, method}:
                    raise ValueError("Unsafe product name")
                path = self.root / "objects" / command.file_id / "enrichments" / f"{kind}--{method}.json"
                payload = artifact.standard_data.model_dump(mode="json")
                publish_product(self.root, path, payload)
                metadata = {**response.metadata, **artifact.metadata, **command.provenance,
                    "artifact_id": artifact.id, "method": response.processor.name, "version": response.processor.version,
                    "input_extraction_id": command.input_revision.representation_id,
                    "input_text_sha256": command.input_revision.text_sha256,
                    "expert_context_supplied": bool(command.request.expert_context), "expert_context": command.request.expert_context,
                    "provenance": provenance}
                meta_path = path.with_suffix(".meta.json")
                atomic_write_text(meta_path, json.dumps(metadata, ensure_ascii=False))
                results.append({"scope_type": "object", "file_id": command.file_id, "kind": artifact.kind,
                    "method": method, "data_path": path.relative_to(self.root).as_posix(),
                    "metadata_path": meta_path.relative_to(self.root).as_posix()})
            clear_artifacts_stale(self.root, command.file_id, "enrichments")
            return {"artifacts": results}
