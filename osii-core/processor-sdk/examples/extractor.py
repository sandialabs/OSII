"""Minimal text extractor. Run with: uvicorn extractor:app --port 8092."""

import base64

from osii_processor_sdk import (
    Capability,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    create_processor_app,
)


class PlainTextExtractor(Extractor):
    descriptor = ProcessorDescriptor(
        name="example.plain-text",
        version="1.0.0",
        display_name="Plain Text Extractor",
        description="Decodes UTF-8 text into one grounded segment.",
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(media_types=["text/plain"], file_extensions=[".txt"]),
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        encoded = request.document.content_base64 or ""
        text = base64.b64decode(encoded).decode(
            request.config.get("encoding", "utf-8"),
        )
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=[
                TextSegment(
                    id="document",
                    text=text,
                    segment_type="document",
                    source_origin={"filename": request.document.filename},
                )
            ],
        )


app = create_processor_app(PlainTextExtractor())

