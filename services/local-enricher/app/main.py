from __future__ import annotations

import re
from collections import Counter

from osii_processor_sdk import (
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
        display_name="Local Statistics and Keywords",
        description="Creates a standard table of document statistics and frequent keywords.",
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


app = create_processor_app(LocalStatsKeywordsEnricher())

