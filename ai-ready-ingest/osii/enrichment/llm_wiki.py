from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar
import uuid

from osii_processor_sdk import DocumentInput, ProcessorClient, ScopeInput, SynthesisRequest

from osii.domain.artifacts.enrichment_artifacts import write_scope_enrichment_variant
from osii.domain.model_provider_config import selected_processor
from osii.domain.read.docs import get_doc_meta
from osii.domain.scopes.scopes import normalize_scope_type
from osii.enrichment.base import BaseEnricher, EnrichmentState
from osii.enrichment.common import collect_scope_texts
from osii.processors.remote import resolve_remote_processor


WIKI_INSTRUCTIONS = """Create a useful, grounded wiki page from the supplied sources.

Begin with the requested level-one title. Do not preface the wiki with commentary.
Use Markdown and organize the page with these sections when the source material supports them:
- Overview
- Key topics or concepts
- Important details
- Source guide
- Caveats and open questions

Use source file IDs in square brackets after factual claims, for example [sha256-example].
Do not invent facts, resolve ambiguities without evidence, or cite a source that does not support
the nearby statement. State clearly when the sources do not provide enough information."""


def _normalize_wiki_markdown(
    markdown: str,
    title: str,
    documents: list[DocumentInput],
) -> tuple[str, bool]:
    normalized = markdown.strip()
    if normalized.startswith("# "):
        _, separator, remainder = normalized.partition("\n")
        normalized = f"# {title}{separator}{remainder}"
    else:
        normalized = f"# {title}\n\n{normalized}"

    source_footer_added = "## Sources" not in normalized
    if source_footer_added:
        sources = "\n".join(
            f"- `[{document.file_id}]` — {document.filename}"
            for document in documents
            if document.file_id
        )
        normalized = f"{normalized}\n\n## Sources\n\n{sources or '_No source identifiers were returned._'}"
    return normalized + "\n", source_footer_added


def _bounded_input_documents(
    osii_store: Path,
    texts: list[dict],
    max_input_chars: int,
) -> tuple[list[DocumentInput], bool]:
    if not texts:
        return [], False

    per_document = max(1, max_input_chars // len(texts))
    remaining = max_input_chars
    truncated = False
    documents: list[DocumentInput] = []

    for index, item in enumerate(texts):
        slots_left = len(texts) - index
        allowance = min(per_document, max(1, remaining // slots_left))
        full_text = str(item.get("text") or "")
        selected_text = full_text[:allowance]
        truncated = truncated or len(selected_text) < len(full_text)
        remaining -= len(selected_text)

        meta = get_doc_meta(osii_store, item["file_id"]) or {}
        file_meta = meta.get("file", {})
        documents.append(
            DocumentInput(
                file_id=item["file_id"],
                filename=str(file_meta.get("filename") or item["file_id"]),
                media_type=str(file_meta.get("mime") or "text/plain"),
                text=selected_text,
                metadata={
                    "representation": item.get("representation"),
                    "source_relpath": file_meta.get("source_relpath"),
                    "input_truncated": len(selected_text) < len(full_text),
                },
            )
        )

    return documents, truncated


class LlmWikiEnricher(BaseEnricher):
    """Compose the selected model-backed synthesizer into a wiki enrichment."""

    name = "llm_wiki"
    display_name = "LLM Wiki"
    description = "Creates a grounded Markdown wiki using the selected model provider."
    version = "1.0"
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "instructions": {
                "type": "string",
                "title": "LLM Wiki prompt",
                "description": "Grounding and structure instructions sent to the selected synthesizer.",
                "default": WIKI_INSTRUCTIONS,
                "format": "textarea",
            },
            "title": {"type": "string", "title": "Default wiki title", "default": "OSII LLM Wiki"},
            "max_input_chars": {
                "type": "integer", "title": "Maximum input characters",
                "minimum": 4000, "maximum": 250000, "default": 60000,
            },
            "max_tokens": {
                "type": "integer", "title": "Maximum output tokens",
                "minimum": 512, "maximum": 4000, "default": 1800,
            },
            "max_brief_documents": {
                "type": "integer", "title": "Maximum source briefs",
                "description": "For small collections, summarize each source before building the wiki.",
                "minimum": 0, "maximum": 20, "default": 8,
            },
        },
        "additionalProperties": False,
    }

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        config = enricher_config or {}
        state = EnrichmentState()
        try:
            scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))
            texts, total_chars = collect_scope_texts(osii_store, scope)
            if not texts:
                raise RuntimeError("No extracted text is available in this scope.")

            state.input_objects_seen = len(texts)
            state.input_chars_read = total_chars
            max_input_chars = max(4_000, min(int(config.get("max_input_chars", 60_000)), 250_000))
            documents, truncated = _bounded_input_documents(osii_store, texts, max_input_chars)

            synthesizer_name = str(
                config.get("synthesizer_name")
                or selected_processor("synthesizer", osii_root=osii_store)
            ).strip()
            if synthesizer_name in {"", "firstN", "recursive", "local.extractive-preview"}:
                raise RuntimeError(
                    "LLM Wiki requires a model-backed synthesizer. Select an Ollama or "
                    "OpenAI-compatible synthesis model in Tools, then try again."
                )

            descriptor = resolve_remote_processor(synthesizer_name, "synthesizer")
            client = ProcessorClient(descriptor["base_url"])
            title = str(config.get("title") or "OSII LLM Wiki").strip() or "OSII LLM Wiki"
            instructions = str(config.get("instructions") or WIKI_INSTRUCTIONS).strip()
            context_parts = [instructions, f"The wiki title is: {title}."]
            if expert_context:
                context_parts.append(f"Additional subject-matter guidance:\n{expert_context.strip()}")

            wiki_documents = documents
            max_brief_documents = max(0, min(int(config.get("max_brief_documents", 8)), 20))
            brief_count = 0
            if scope_type == "collection" and 1 < len(documents) <= max_brief_documents:
                wiki_documents = []
                for document in documents:
                    brief_request_id = str(uuid.uuid4())
                    brief = client.synthesize(
                        SynthesisRequest(
                            request_id=brief_request_id,
                            scope=ScopeInput(
                                scope_type="object",
                                scope_id=str(document.file_id or document.filename),
                                documents=[document],
                                metadata={"knowledge_product_stage": "source_brief"},
                            ),
                            expert_context=expert_context,
                            config={
                                "instructions": (
                                    "Create a concise factual brief for this one source. Preserve its file ID, "
                                    "distinct topics, important procedures or claims, and caveats. Do not add facts."
                                ),
                                "max_tokens": 500,
                                **({"model": config["model"]} if config.get("model") else {}),
                            },
                        )
                    )
                    if brief.request_id != brief_request_id:
                        raise RuntimeError("Synthesizer returned a mismatched source-brief request ID.")
                    wiki_documents.append(
                        document.model_copy(
                            update={
                                "text": brief.markdown,
                                "metadata": {
                                    **document.metadata,
                                    "knowledge_product_stage": "source_brief",
                                },
                            }
                        )
                    )
                    brief_count += 1

            request_id = str(uuid.uuid4())
            response = client.synthesize(
                SynthesisRequest(
                    request_id=request_id,
                    scope=ScopeInput(
                        scope_type=scope_type,
                        scope_id=str(
                            scope.get("file_id")
                            or scope.get("folder_id")
                            or scope.get("collection_id")
                            or "root"
                        ),
                        documents=wiki_documents,
                        metadata={"knowledge_product": "llm_wiki", "title": title},
                    ),
                    expert_context="\n\n".join(context_parts),
                    config={
                        "instructions": instructions,
                        "title": title,
                        "max_tokens": max(512, min(int(config.get("max_tokens", 1_800)), 4_000)),
                        **({"model": config["model"]} if config.get("model") else {}),
                    },
                )
            )
            if response.request_id != request_id:
                raise RuntimeError("Synthesizer returned a mismatched request ID.")

            citations = [item.model_dump(mode="json") for item in response.citations]
            markdown, source_footer_added = _normalize_wiki_markdown(
                response.markdown,
                title,
                documents,
            )
            result = write_scope_enrichment_variant(
                osii_store,
                scope,
                kind="wiki",
                method=self.name,
                payload={
                    "artifact_type": "wiki_markdown",
                    "title": title,
                    "markdown": markdown,
                    "citations": citations,
                },
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "processor": response.processor.name,
                    "processor_version": response.processor.version,
                    "model": response.metadata.get("model"),
                    "provider": response.metadata.get("provider"),
                    "input_object_count": len(documents),
                    "input_chars_available": total_chars,
                    "input_chars_sent": sum(len(document.text or "") for document in documents),
                    "final_input_chars": sum(len(document.text or "") for document in wiki_documents),
                    "input_truncated": truncated,
                    "hierarchical_source_briefs": brief_count,
                    "source_footer_added": source_footer_added,
                    "expert_context_used": bool(expert_context),
                    "citations": citations,
                    **response.metadata,
                },
            )
            state.output_files_written = 2
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error) from exc
