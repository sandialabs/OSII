"""Storage-independent baseline processors shared by local hosts and hosted workers."""
from __future__ import annotations

from osii.processor_sdk import (
    Capability,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    SynthesisRequest,
    SynthesisResponse,
    Synthesizer,
    create_processor_app,
)


class LocalExtractivePreviewSynthesizer(Synthesizer):
    descriptor = ProcessorDescriptor(
        name="local.extractive-preview",
        version="1.0.1",
        display_name="Cited source-excerpt preview (no AI)",
        description=(
            "Model-free synthesis over text that has already been extracted. It selects "
            "short source excerpts and formats them as cited Markdown; it does not run OCR, "
            "interpret the document, or generate new claims."
        ),
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(
            scope_types=["object", "folder", "collection", "root"],
            output_kinds=["wiki_markdown"],
        ),
        config_schema={
            "type": "object",
            "properties": {"max_chars_per_document": {"type": "integer", "minimum": 100, "default": 1000}},
            "additionalProperties": False,
        },
    )

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        max_chars = int(request.config.get("max_chars_per_document", 1000))
        sections: list[str] = []
        citations: list[ProvenanceRef] = []
        for document in request.scope.documents:
            text = document.text or "\n\n".join(segment.text for segment in document.segments)
            excerpt, start, end = source_excerpt(text, max_chars)
            if not excerpt:
                continue
            sections.append(f"## {document.filename}\n\n{excerpt}")
            if document.file_id:
                citations.append(ProvenanceRef(file_id=document.file_id, char_start=start, char_end=end))
        return SynthesisResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            markdown="\n\n".join(sections),
            citations=citations,
            metadata={"mode": "extractive_preview", "document_count": len(sections), **suggested_title(request, "", model_generated=False)},
            warnings=[] if sections else ["No text content was available for an extractive preview."],
        )



import re
from collections import Counter

from osii.processor_sdk import (
    Artifact,
    Capability,
    Enricher,
    EnrichmentRequest,
    EnrichmentResponse,
    ProcessorDescriptor,
    ProcessorKind,
    TableArtifactData,
    TableColumn,
    create_processor_app,
)


STOPWORDS = {"the", "and", "for", "are", "with", "that", "this", "from", "was", "were", "have", "has", "into", "document", "report"}


class LocalStatsKeywordsEnricher(Enricher):
    descriptor = ProcessorDescriptor(
        name="local.stats-keywords",
        version="1.0.0",
        display_name="Document statistics and frequent keywords",
        description=(
            "Counts characters and words and lists frequent terms from extracted text. "
            "It is deterministic Python processing and does not call an AI model."
        ),
        kind=ProcessorKind.ENRICHER,
        capabilities=Capability(
            scope_types=["object", "folder", "collection", "root"],
            output_kinds=["table"],
        ),
        config_schema={
            "type": "object",
            "properties": {"top_k": {"type": "integer", "minimum": 1, "default": 20}},
            "additionalProperties": False,
        },
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        top_k = int(request.config.get("top_k", 20))
        rows = []
        for document in request.scope.documents:
            text = document.text or "\n\n".join(segment.text for segment in document.segments)
            words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
            keywords = [word for word, _ in Counter(word for word in words if word not in STOPWORDS).most_common(top_k)]
            rows.append({
                "file_id": document.file_id or "",
                "filename": document.filename,
                "characters": len(text),
                "words": len(words),
                "keywords": keywords,
            })
        table = TableArtifactData(
            title="Document statistics and keywords",
            description="Deterministic local measurements of preferred document text.",
            columns=[
                TableColumn(key="file_id", label="File ID"),
                TableColumn(key="filename", label="Filename"),
                TableColumn(key="characters", label="Characters", data_type="integer"),
                TableColumn(key="words", label="Words", data_type="integer"),
                TableColumn(key="keywords", label="Keywords", data_type="json"),
            ],
            rows=rows,
        )
        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[Artifact(id="document-statistics", kind="table", media_type="application/json", standard_data=table)],
            metadata={"document_count": len(rows)},
        )


DEFAULT_SYNTHESIS_INSTRUCTIONS = (
    "Write a concise grounded Mathpix Markdown synthesis. Use LaTeX math delimiters for mathematical notation and preserve tables when useful. Cite source file IDs in square "
    "brackets. Do not introduce facts absent from the sources. Begin with # followed by a concise descriptive document title inferred from the content, not an opaque filename."
)


def synthesis_prompt(request: SynthesisRequest) -> str:
    sources = []
    for document in request.scope.documents:
        text = document.text or "\n\n".join(segment.text for segment in document.segments)
        sources.append(f"SOURCE {document.file_id or document.filename}:\n{text}")
    instructions = str(request.config.get("instructions") or DEFAULT_SYNTHESIS_INSTRUCTIONS).strip()
    context = str(request.expert_context or "").strip()
    guidance = f"\n\nADDITIONAL GUIDANCE:\n{context}" if context else ""
    return f"{instructions}{guidance}\n\n" + "\n\n".join(sources)


def chat_synthesizer_descriptor(provider: str = "openai") -> ProcessorDescriptor:
    return ProcessorDescriptor(
        name=f"{provider}.synthesizer",
        version="1.2.1",
        display_name=f"{provider.title()} Synthesizer",
        description=f"Processor API adapter for an explicitly selected {provider} chat model.",
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(batch_reduction="wiki", scope_types=["object", "folder", "collection", "root"], output_kinds=["wiki_markdown"]),
        config_schema={
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string", "title": "Synthesis prompt",
                    "description": "Instructions placed before the grounded source material.",
                    "default": DEFAULT_SYNTHESIS_INSTRUCTIONS, "format": "textarea",
                },
                "temperature": {
                    "type": "number", "title": "Temperature",
                    "description": "Lower values make synthesis more repeatable.",
                    "minimum": 0, "maximum": 2, "default": 0.2,
                },
                "extract_metadata": {"type":"boolean", "title":"Suggest document metadata", "description":"One additional text-model call per document; fields may be blank or qualified.", "default":True},
                "window_chars": {"type":"integer", "title":"Characters per synthesis window", "minimum":4000, "maximum":160000, "default":100000},
                "max_input_windows": {"type":"integer", "title":"Maximum input windows", "minimum":1, "maximum":64, "default":32},
                "max_tokens": {
                    "type": "integer", "title": "Maximum output tokens",
                    "minimum": 256, "maximum": 4000, "default": 1200,
                },
            },
            "additionalProperties": False,
        },
    )


def model_synthesis_response(request: SynthesisRequest, descriptor: ProcessorDescriptor,
                             markdown: str, model: str, metadata: dict | None = None) -> SynthesisResponse:
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Provider returned empty synthesis text.")
    return SynthesisResponse(request_id=request.request_id, processor=descriptor, markdown=markdown.strip(),
        citations=[ProvenanceRef(file_id=doc.file_id) for doc in request.scope.documents if doc.file_id],
        metadata={**(metadata or {}), "model": model, **suggested_title(request, markdown, model_generated=True)})


def source_excerpt(text: str, max_chars: int) -> tuple[str, int, int]:
    """Normalize display whitespace while retaining the original source span."""
    excerpt, start, end = "", 0, 0
    for match in re.finditer(r"\S+", text):
        separator = " " if excerpt else ""
        remaining = max_chars - len(excerpt) - len(separator)
        if remaining <= 0:
            break
        part = match.group()[:remaining]
        if not excerpt:
            start = match.start()
        excerpt += separator + part
        end = match.start() + len(part)
        if len(part) < len(match.group()):
            break
    return excerpt, start, end


def suggested_title(request: SynthesisRequest, markdown: str, *, model_generated: bool) -> dict:
    if len(request.scope.documents) != 1:
        return {}
    candidate = next((line.lstrip('#').strip() for line in markdown.splitlines() if line.startswith('#')), '')
    if candidate.casefold() in {'summary','document summary','synthesis','overview','source excerpts','analysis'}:
        candidate = ''
    method = 'model_generated' if candidate and model_generated else 'source_first_line'
    if not candidate:
        candidate = next((line.strip() for line in (request.scope.documents[0].text or '')[:4000].splitlines()
                          if 5 <= len(line.strip()) <= 160 and sum(char.isalpha() for char in line)>4), '')
    candidate = re.sub(r'[<>\x00-\x1f]', '', candidate).strip(' #*`"')[:160].strip()
    if not candidate or candidate == request.scope.documents[0].filename:
        return {}
    return {'document_title': candidate, 'title_method': method}
