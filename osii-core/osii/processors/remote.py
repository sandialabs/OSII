from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
import base64
import mimetypes
from pathlib import Path
from osii.expert_context import resolve_expert_context
from typing import Any

from osii.configuration import (
    configured_tools,
    model_connection,
    tool_for_processor,
    resolve_tool_models,
)
from osii.model_gateway_tokens import issue_model_gateway_token

from osii.processor_sdk import (
    DocumentInput,
    EmbeddingInput,
    EmbeddingRequest,
    ExtractionRequest,
    ProcessorClient,
    ProcessorDescriptor,
    ProcessorClientError,
    ScopeInput,
    SynthesisRequest,
)

from osii.enrichment.common import collect_scope_texts
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.read.docs import get_doc_meta
from osii.domain.read.sidecar import SidecarLibraryReader
from osii.domain.storage.commits import (InputRevision, ProcessingCommit, ScopeInputRevision,
    ScopeProcessingCommit, CommitConflict, text_digest)
from osii.domain.read.contracts import ReadScope
from osii.domain.storage.sidecar_commits import SidecarProcessingCommitter
from osii.extraction.base import ExtractionArtifact, ExtractionSegment, ExtractionState
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    persist_artifact,
    persist_segment,
    update_provenance,
)
from osii.processor_sdk.document_metadata import DocumentMetadata


def _commit_input(root: Path, file_id: str) -> InputRevision:
    from osii.enrichment.common import frozen_object_text
    frozen = frozen_object_text(root, file_id)
    if frozen and frozen.get("source_sha256"):
        return InputRevision(file_id,
            "edited" if frozen.get("representation") == "edited" else frozen.get("extraction_id") or "canonical",
            frozen["source_sha256"])
    return InputRevision.capture(SidecarLibraryReader(root), file_id)


def _commit_scope_input(root: Path, scope: dict, texts: list[dict]) -> ScopeInputRevision:
    from osii.domain.artifacts.products import current_product_provenance
    from osii.domain.scopes.membership import list_scope_file_ids
    context = current_product_provenance()
    if "processing_revision" in context:
        revision = ScopeInputRevision.from_dict(context["processing_revision"])
    elif "member_ids" in context and context.get("inputs"):
        # Compatibility for already queued, bounded input snapshots.
        revision = ScopeInputRevision(tuple(sorted(context["member_ids"])), tuple(sorted((
            InputRevision(row["file_id"], "edited" if row.get("representation") == "edited" else row.get("extraction_id") or "canonical",
                row["source_sha256"]) for row in context["inputs"]), key=lambda row: row.file_id)))
    else:
        revision = ScopeInputRevision.capture(SidecarLibraryReader(root), list_scope_file_ids(root, scope))
    inputs = {row.file_id: row for row in revision.inputs}
    for document in texts:
        expected = inputs.get(document["file_id"])
        if expected is None or expected.text_sha256 != (document.get("source_sha256") or text_digest(document["text"])):
            raise CommitConflict("Scope input text changed while staging the request")
    return revision


def _commit_context(request_id: str, file_id: str, kind: str) -> tuple[str, dict]:
    from osii.domain.artifacts.products import current_product_provenance
    context = current_product_provenance()
    operation = f"{context['run_id']}:{file_id}:{kind}" if context.get("run_id") else request_id
    return operation, context


def _commit_descriptor(descriptor: dict) -> ProcessorDescriptor:
    return ProcessorDescriptor.model_validate({key: value for key, value in descriptor.items()
        if key in ProcessorDescriptor.model_fields})


def configured_processor_urls() -> list[str]:
    configured = [
        value.strip().rstrip("/")
        for value in os.getenv("OSII_PROCESSORS", "").split(",")
        if value.strip()
    ]
    osii_root = os.getenv("OSII_ROOT")
    if osii_root:
        root = Path(osii_root).expanduser()
        for tool in configured_tools(root).values():
            if not isinstance(tool, dict) or not tool.get("enabled", True):
                continue
            runtime = tool.get("runtime") or {}
            endpoint = str(runtime.get("endpoint") or "").strip().rstrip("/")
            if endpoint:
                configured.append(endpoint)
        state_path = Path(osii_root).expanduser() / "state"
        registry_path = state_path / "processor_endpoints.json"
        try:
            endpoints = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            endpoints = []
        for endpoint in endpoints:
            if endpoint.get("enabled") and endpoint.get("base_url"):
                configured.append(str(endpoint["base_url"]).rstrip("/"))
        try:
            providers = json.loads((state_path / "model_providers.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            providers = []
        bridge_url = os.getenv("OSII_MODEL_BRIDGE_URL", "http://127.0.0.1:8095").rstrip("/")
        for provider in providers:
            if not provider.get("enabled"):
                continue
            provider_type = provider.get("type")
            if provider_type in {"ollama", "openai"}:
                configured.extend([f"{bridge_url}/{provider_type}/embedder", f"{bridge_url}/{provider_type}/synthesizer"])

    # An endpoint may be configured in both places; only probe it once.
    return list(dict.fromkeys(configured))


def _model_context(
    *,
    processor_name: str,
    descriptor: dict[str, Any],
    request_id: str,
    osii_root: Path,
) -> dict[str, Any] | None:
    requirements = descriptor.get("model_requirements") or {}
    if not requirements:
        return None
    configured = tool_for_processor(processor_name, osii_root)
    tool_id = configured[0] if configured else processor_name
    from osii.domain.tool_actions import frozen_bindings
    bindings = frozen_bindings(processor_name)
    if bindings is None:
        bindings = resolve_tool_models(processor_name, requirements, osii_root)
    if not bindings:
        return None
    return {
        "gateway_url": os.getenv(
            "OSII_MODEL_GATEWAY_PUBLIC_URL", "http://127.0.0.1:8095/v1"
        ).rstrip("/"),
        "token": issue_model_gateway_token(
            tool_id=tool_id,
            job_id=request_id,
            bindings=bindings,
            connection_fingerprints={cap: hashlib.sha256(json.dumps(model_connection(alias, osii_root), sort_keys=True).encode()).hexdigest() for cap, alias in bindings.items()},
        ),
        "bindings": bindings,
    }


def _request_json(url: str, *, payload: dict | None = None, timeout: float = 120.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Processor request to {url} failed: {exc}") from exc


def _revoke_model_context(context: dict[str, Any] | None) -> None:
    """Best-effort revocation once the synchronous processor job has ended."""
    if not context:
        return
    request = urllib.request.Request(
        f"{str(context['gateway_url']).rstrip('/')}/tokens/revoke",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {context['token']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3):
            pass
    except (urllib.error.URLError, OSError):
        # Expiration and request bounds still constrain a grant if a gateway
        # disappears before Core can explicitly revoke it.
        pass


def discover_remote_processors(*, include_errors: bool = False) -> list[dict[str, Any]]:
    discovered = []
    for base_url in configured_processor_urls():
        try:
            descriptor = ProcessorDescriptor.model_validate(
                _request_json(f"{base_url}/v1/descriptor", timeout=5.0)
            ).model_dump(mode="json")
            descriptor["base_url"] = base_url
            descriptor["remote"] = True
            discovered.append(descriptor)
        except (RuntimeError, ValueError, TypeError) as exc:
            if include_errors:
                discovered.append({"base_url": base_url, "remote": True, "error": str(exc)})
    return discovered


def resolve_remote_processor(name: str, kind: str) -> dict[str, Any]:
    for descriptor in discover_remote_processors():
        if descriptor.get("name") == name and descriptor.get("kind") == kind:
            return descriptor
        osii_root = os.getenv("OSII_ROOT")
        if osii_root and descriptor.get("kind") == kind:
            configured = tool_for_processor(name, Path(osii_root).expanduser())
            if configured and configured[1].get("processor_id") == descriptor.get("name"):
                return descriptor
    raise RuntimeError(f"Processor '{name}' ({kind}) is not registered or unavailable.")


class RemoteProcessorUnavailable(RuntimeError):
    """A remote operation failed before core began a canonical commit."""


class RemoteExtractor:
    def __init__(self, descriptor: dict[str, Any]) -> None:
        self._descriptor = descriptor
        self.base_url = descriptor["base_url"]
        self.name = descriptor["name"]
        self.version = descriptor["version"]
        self.display_name = descriptor["display_name"]
        self.description = descriptor["description"]
        self._client = ProcessorClient(self.base_url)

    def describe(self) -> dict[str, Any]:
        return dict(self._descriptor)

    def extract(
        self,
        *,
        source_path: Path,
        data_volume_root: Path,
        osii_store: Path,
        expert_context: str | None = None,
        extractor_config: dict | None = None,
    ) -> dict:
        doc_ctx = init_doc_context(source_path, data_volume_root)
        expert_context = resolve_expert_context(
            osii_store, {"scope_type": "object", "file_id": doc_ctx["file_id"]}, expert_context
        )
        # Record supplied guidance, not a claim that the remote processor used it.
        provenance_config = {
            **(extractor_config or {}),
            "expert_context_supplied": bool(expert_context),
            "expert_context": expert_context,
        }
        state = ExtractionState()
        request_id = str(uuid.uuid4())
        model_context = _model_context(
            processor_name=self.name,
            descriptor=self._descriptor,
            request_id=request_id,
            osii_root=osii_store,
        )
        try:
            response = self._client.extract(ExtractionRequest(
                request_id=request_id,
                document=DocumentInput(
                    file_id=doc_ctx["file_id"],
                    filename=source_path.name,
                    media_type=doc_ctx["mime"],
                    content_base64=base64.b64encode(source_path.read_bytes()).decode("ascii"),
                    metadata={"source_relpath": doc_ctx["source_relpath"]},
                ),
                expert_context=expert_context,
                config=extractor_config or {},
                model_context=model_context,
            ))
        except ProcessorClientError as exc:
            raise RemoteProcessorUnavailable(str(exc)) from exc
        finally:
            _revoke_model_context(model_context)
        initialize_bundle(osii_store=osii_store, doc_ctx=doc_ctx)
        update_provenance(
            osii_store=osii_store,
            doc_ctx=doc_ctx,
            extractor_name=self.name,
            extractor_version=self.version,
            status="running",
            tools={"processor_url": self.base_url},
            config=provenance_config,
            state=state,
        )
        try:
            if response.request_id != request_id:
                raise RuntimeError("Extractor returned a mismatched request_id.")
            if not response.segments:
                detail = "; ".join(response.warnings) or "Processor returned no text segments."
                raise RuntimeError(detail)
            state.units_attempted = len(response.segments)
            for index, segment in enumerate(response.segments, start=1):
                persist_segment(
                    osii_store=osii_store,
                    doc_ctx=doc_ctx,
                    segment=ExtractionSegment(
                        seg=index,
                        type=segment.segment_type,
                        text=segment.text,
                        source_origin={**segment.source_origin, "processor_segment_id": segment.id},
                        related_ids=segment.related_ids,
                    ),
                    shared_text_file=True,
                )
                state.segments_written += 1
                state.units_completed += 1
            for index, artifact in enumerate(response.artifacts, start=1):
                if artifact.data_base64 is not None:
                    data = base64.b64decode(artifact.data_base64)
                elif artifact.text is not None:
                    data = artifact.text.encode("utf-8")
                else:
                    payload = artifact.json_data if artifact.json_data is not None else artifact.standard_data.model_dump(mode="json")
                    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                extension = mimetypes.guess_extension(artifact.media_type) or (".json" if artifact.media_type == "application/json" else ".bin")
                persist_artifact(
                    osii_store=osii_store,
                    doc_ctx=doc_ctx,
                    artifact=ExtractionArtifact(
                        artifact_id=artifact.id,
                        kind=artifact.kind,
                        type=artifact.media_type,
                        extension=extension,
                        data=data,
                        source_origin=artifact.source_origin,
                    ),
                    artifact_num=index,
                )
                state.artifacts_written += 1
            state.warnings.extend(response.warnings)
            status = "done"
        except Exception as exc:
            state.error = str(exc)
            status = "error"
        update_provenance(
            osii_store=osii_store,
            doc_ctx=doc_ctx,
            extractor_name=self.name,
            extractor_version=self.version,
            status=status,
            tools={"processor_url": self.base_url},
            config=provenance_config,
            state=state,
        )
        if state.error:
            raise RuntimeError(state.error)
        return build_result_dict(doc_ctx)


class RemoteSynthesizer:
    def __init__(self, descriptor: dict[str, Any]) -> None:
        self._descriptor = descriptor
        self.base_url = descriptor["base_url"]
        self.name = descriptor["name"]
        self.version = descriptor["version"]
        self.display_name = descriptor["display_name"]
        self.description = descriptor["description"]
        self._client = ProcessorClient(self.base_url)

    def describe(self) -> dict[str, Any]:
        return dict(self._descriptor)

    def synthesize(
        self,
        *,
        osii_store: Path,
        file_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        from osii.enrichment.common import frozen_object_text
        from osii.domain.tool_actions import frozen_expert_context
        preferred = frozen_object_text(osii_store, file_id)
        if preferred is None:
            preferred = get_preferred_text_representation(osii_store, file_id)
        frozen, context = frozen_expert_context(self.name)
        expert_context = context if frozen else resolve_expert_context(
            osii_store, {"scope_type": "object", "file_id": file_id}, expert_context
        )
        meta = get_doc_meta(osii_store, file_id) or {}
        file_meta = meta.get("file", {})
        if preferred is None:
            raise RuntimeError(f"No preferred text is available for {file_id}.")
        input_revision = _commit_input(osii_store, file_id)
        request_id = str(uuid.uuid4())
        model_context = _model_context(
            processor_name=self.name,
            descriptor=self._descriptor,
            request_id=request_id,
            osii_root=osii_store,
        )
        try:
            request = SynthesisRequest(
                request_id=request_id,
                scope=ScopeInput(
                    scope_type="object",
                    scope_id=file_id,
                    documents=[DocumentInput(
                        file_id=file_id,
                        filename=file_meta.get("filename") or file_id,
                        media_type=file_meta.get("mime") or "text/plain",
                        text=preferred.get("text") or "",
                        metadata={"representation": preferred.get("name")},
                    )],
                ),
                expert_context=expert_context,
                config=synthesizer_config or {},
                model_context=model_context,
            )
            response = self._client.synthesize(request)
        finally:
            _revoke_model_context(model_context)
        if response.request_id != request_id:
            raise RuntimeError("Synthesizer returned a mismatched request_id.")
        if response.metadata.get("document_metadata"):
            response.metadata["document_metadata"] = DocumentMetadata.model_validate(response.metadata["document_metadata"]).model_dump(mode="json", exclude_none=True)
        operation, provenance = _commit_context(request_id, file_id, "synthesis")
        saved = SidecarProcessingCommitter(osii_store).commit(ProcessingCommit(operation, file_id,
            request, response, _commit_descriptor(self._descriptor), input_revision=input_revision,
            provenance={**provenance, "processor_url": self.base_url}))
        return {
            "file_id": file_id,
            **saved.result,
            "error": None,
        }

    def synthesize_scope(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        """Synthesize and commit a folder, collection, or root scope."""
        expert_context = resolve_expert_context(osii_store, scope, expert_context)
        scope_type = (scope.get("scope_type") or scope.get("type") or "").strip().lower()
        if scope_type not in {"folder", "collection", "root"}:
            raise ValueError("Aggregate synthesis scope must be folder, collection, or root.")
        texts, _ = collect_scope_texts(osii_store, scope)
        scope_id = str(scope.get("folder_id") or scope.get("collection_id") or "root")
        input_revision = _commit_scope_input(osii_store, scope, texts)
        request_id = str(uuid.uuid4())
        model_context = _model_context(
            processor_name=self.name,
            descriptor=self._descriptor,
            request_id=request_id,
            osii_root=osii_store,
        )
        try:
            request = SynthesisRequest(
                request_id=request_id,
                scope=ScopeInput(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    documents=[DocumentInput(
                        file_id=item["file_id"],
                        filename=item.get("path") or item["file_id"],
                        media_type="text/plain",
                        text=item["text"],
                        metadata={"representation": item.get("representation")},
                    ) for item in texts],
                ),
                expert_context=expert_context,
                config=synthesizer_config or {},
                model_context=model_context,
            )
            response = self._client.synthesize(request)
        finally:
            _revoke_model_context(model_context)
        if response.request_id != request_id:
            raise RuntimeError("Synthesizer returned a mismatched request_id.")
        operation, provenance = _commit_context(request_id, f"{scope_type}:{scope_id}", "synthesis")
        saved = SidecarProcessingCommitter(osii_store).commit(ScopeProcessingCommit(operation,
            ReadScope(scope_type, scope_id), request, response, _commit_descriptor(self._descriptor), input_revision,
            provenance={**provenance, "processor_url": self.base_url}))
        return {"ok": True, "result": saved.result, "error": None}


class ProcessorEmbeddingClient:
    def __init__(self, descriptor: dict[str, Any]) -> None:
        self.descriptor = descriptor
        self.base_url = descriptor["base_url"]
        self._client = ProcessorClient(self.base_url)
        self.model_name = descriptor["name"]
        self.provider = descriptor["name"]
        self.dimensions: int | None = None
        self.model_digest: str | None = None
        self.normalized: bool | None = None
        self.endpoint_type: str | None = None
        self.semantic: bool | None = None

    def embed(self, *, model: str, texts) -> list[list[float]]:
        request_id = str(uuid.uuid4())
        identifiers = [f"input-{index}" for index in range(len(texts))]
        model_context = _model_context(
            processor_name=self.descriptor["name"],
            descriptor=self.descriptor,
            request_id=request_id,
            osii_root=Path(os.getenv("OSII_ROOT", "./osii-data/.osii")).expanduser(),
        )
        try:
            response = self._client.embed(EmbeddingRequest(
                request_id=request_id,
                inputs=[EmbeddingInput(id=identifier, text=text) for identifier, text in zip(identifiers, texts)],
                config={"model": model} if model else {},
                model_context=model_context,
            ))
        finally:
            _revoke_model_context(model_context)
        if response.request_id != request_id:
            raise RuntimeError("Embedder returned a mismatched request_id.")
        by_id = {item.id: item for item in response.vectors}
        if set(by_id) != set(identifiers):
            raise RuntimeError("Embedder did not return exactly one vector for each input ID.")
        dimensions = {item.dimensions for item in response.vectors}
        if len(dimensions) != 1:
            raise RuntimeError("Embedder returned inconsistent vector dimensions.")
        self.model_name = response.model
        self.provider = response.processor.name
        self.dimensions = next(iter(dimensions))
        self.model_digest = response.metadata.get("model_digest")
        self.normalized = response.normalized
        self.endpoint_type = response.metadata.get("endpoint_type")
        self.semantic = response.metadata.get("semantic")
        return [by_id[identifier].vector for identifier in identifiers]


class RemoteEnricher:
    def __init__(self, descriptor: dict[str, Any]) -> None:
        self._descriptor = descriptor
        self.base_url = descriptor["base_url"]
        self.name = descriptor["name"]
        self.version = descriptor["version"]
        self.display_name = descriptor["display_name"]
        self.description = descriptor["description"]
        self.model_requirements = descriptor.get("model_requirements") or {}

    def describe(self) -> dict[str, Any]:
        return dict(self._descriptor)

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        texts, _ = collect_scope_texts(osii_store, scope)
        from osii.domain.tool_actions import frozen_expert_context
        frozen, context = frozen_expert_context(self.name)
        expert_context = context if frozen else resolve_expert_context(osii_store, scope, expert_context)
        scope_type = (scope.get("scope_type") or scope.get("type") or "").strip().lower()
        scope_id = (
            scope.get("file_id")
            or scope.get("folder_id")
            or scope.get("collection_id")
            or "root"
        )
        documents = [
            {
                "file_id": item["file_id"],
                "filename": item["file_id"],
                "media_type": "text/plain",
                "text": item["text"],
                "metadata": {
                    "representation": item.get("representation"),
                    "path": item.get("path"),
                },
            }
            for item in texts
        ]

        processor_input = {
            "scope": {
                "scope_type": scope_type,
                "scope_id": str(scope_id),
                "documents": documents,
            }
        }

        request_id = str(uuid.uuid4())
        input_revision = _commit_input(osii_store, str(scope_id)) if scope_type == "object" else None
        scope_revision = _commit_scope_input(osii_store, scope, texts) if scope_type != "object" else None
        model_context = _model_context(
            processor_name=self.name,
            descriptor=self._descriptor,
            request_id=request_id,
            osii_root=osii_store,
        )
        try:
            response = _request_json(
                f"{self.base_url}/v1/enrich",
                payload={
                    "api_version": "v1",
                    "request_id": request_id,
                    **processor_input,
                    "expert_context": expert_context,
                    "config": enricher_config or {},
                    "model_context": model_context,
                },
            )
        finally:
            _revoke_model_context(model_context)
        from osii.processor_sdk import EnrichmentResponse
        if len(json.dumps(response)) > 8_000_000:
            raise ValueError("Processor returned more than 8 MB of enrichment output")
        validated = EnrichmentResponse.model_validate(response)
        if validated.request_id != request_id or validated.processor.name != self.name:
            raise ValueError("Processor returned a response for a different request or tool")
        if scope_type == "object":
            from osii.processor_sdk import EnrichmentRequest
            request = EnrichmentRequest(request_id=request_id, scope=ScopeInput.model_validate(processor_input["scope"]),
                expert_context=expert_context, config=enricher_config or {})
            operation, provenance = _commit_context(request_id, str(scope_id), "enrichment")
            saved = SidecarProcessingCommitter(osii_store).commit(ProcessingCommit(operation, str(scope_id), request,
                validated, _commit_descriptor(self._descriptor), input_revision=input_revision,
                provenance={**provenance, "processor_url": self.base_url}))
            results = saved.result["artifacts"]
            return {"ok": True, "result": results[0], "artifacts": results, "error": None}
        from osii.processor_sdk import EnrichmentRequest
        request = EnrichmentRequest(request_id=request_id, scope=ScopeInput.model_validate(processor_input["scope"]),
            expert_context=expert_context, config=enricher_config or {})
        operation, provenance = _commit_context(request_id, f"{scope_type}:{scope_id}", "enrichment")
        saved = SidecarProcessingCommitter(osii_store).commit(ScopeProcessingCommit(operation,
            ReadScope(scope_type, str(scope_id)), request, validated, _commit_descriptor(self._descriptor), scope_revision,
            provenance={**provenance, "processor_url": self.base_url}))
        results = saved.result["artifacts"]
        return {
            "ok": True,
            "result": results[0],
            "artifacts": results,
            "error": None,
        }
