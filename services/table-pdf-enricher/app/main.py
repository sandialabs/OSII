from __future__ import annotations

import re

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


class TablePdfEnricher(Enricher):
    """Reference SME processor; replace this parser with domain-specific logic."""

    descriptor = ProcessorDescriptor(
        name="example.table-pdf",
        version="0.1.0",
        display_name="Example Table PDF Enricher",
        description="Extracts pipe-delimited table rows from document text.",
        kind=ProcessorKind.ENRICHER,
        capabilities=Capability(
            media_types=["application/pdf", "text/plain"],
            scope_types=["object"],
            output_kinds=["table_rows"],
        ),
        config_schema={
            "type": "object",
            "properties": {
                "delimiter": {"type": "string", "default": "|"},
                "minimum_columns": {"type": "integer", "minimum": 2, "default": 2},
            },
            "additionalProperties": False,
        },
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        if request.scope.scope_type != "object" or len(request.scope.documents) != 1:
            raise ValueError("this example accepts one object scope")
        document = request.scope.documents[0]

        delimiter = str(request.config.get("delimiter", "|"))
        minimum_columns = int(request.config.get("minimum_columns", 2))
        text = document.text or "\n".join(segment.text for segment in document.segments)

        rows: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            cells = [re.sub(r"\s+", " ", value).strip() for value in line.split(delimiter)]
            if len(cells) >= minimum_columns and all(cells):
                rows.append({
                    "line": line_number,
                    **{f"column_{index + 1}": cell for index, cell in enumerate(cells)},
                })

        width = max((len(row) - 1 for row in rows), default=minimum_columns)
        columns = [TableColumn(key="line", label="Source line", data_type="integer")]
        columns.extend(
            TableColumn(key=f"column_{index + 1}", label=f"Column {index + 1}")
            for index in range(width)
        )

        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[
                Artifact(
                    id="table-rows",
                    kind="table_rows",
                    media_type="application/json",
                    standard_data=TableArtifactData(
                        title=f"Extracted table rows — {document.filename}",
                        description="Rows detected by the example pipe-delimited parser.",
                        columns=columns,
                        rows=rows,
                    ),
                    metadata={"row_count": len(rows)},
                )
            ],
            metadata={"input_filename": document.filename},
        )


app = create_processor_app(TablePdfEnricher())
