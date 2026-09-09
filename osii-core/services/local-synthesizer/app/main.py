from __future__ import annotations

from osii_processor_sdk import (
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
        version="1.0.0",
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
            excerpt = " ".join(text.split())[:max_chars].strip()
            if not excerpt:
                continue
            sections.append(f"## {document.filename}\n\n{excerpt}")
            if document.file_id:
                citations.append(ProvenanceRef(file_id=document.file_id, char_start=0, char_end=len(excerpt)))
        return SynthesisResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            markdown="\n\n".join(sections),
            citations=citations,
            metadata={"mode": "extractive_preview", "document_count": len(sections)},
            warnings=[] if sections else ["No text content was available for an extractive preview."],
        )


app = create_processor_app(LocalExtractivePreviewSynthesizer())
