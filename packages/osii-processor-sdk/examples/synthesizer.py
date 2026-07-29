"""Minimal local synthesizer. Replace the first-lines logic with a local LLM."""

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


class FirstLinesSynthesizer(Synthesizer):
    descriptor = ProcessorDescriptor(
        name="example.first-lines",
        version="1.0.0",
        display_name="First Lines Synthesizer",
        description="Creates deterministic Markdown without a model dependency.",
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(scope_types=["object", "folder", "collection", "root"]),
    )

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        sections = []
        citations = []
        for document in request.scope.documents:
            excerpt = (document.text or "").strip()[:500]
            sections.append(f"## {document.filename}\n\n{excerpt}")
            if document.file_id and excerpt:
                citations.append(
                    ProvenanceRef(
                        file_id=document.file_id,
                        char_start=0,
                        char_end=len(excerpt),
                    )
                )
        return SynthesisResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            markdown="\n\n".join(sections),
            citations=citations,
        )


app = create_processor_app(FirstLinesSynthesizer())

