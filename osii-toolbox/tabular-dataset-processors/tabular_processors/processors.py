"""Processor implementations for grounded CSV tables and dataset collections."""

from __future__ import annotations

import base64
import csv
import io
import json
from typing import Any

from osii_processor_sdk import (
    Artifact,
    Capability,
    Enricher,
    EnrichmentRequest,
    EnrichmentResponse,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    TableArtifactData,
    TableColumn,
    TextSegment,
)


def _value(raw: str) -> str | int | float:
    clean = raw.strip()
    try:
        return int(clean)
    except ValueError:
        try:
            return float(clean)
        except ValueError:
            return clean


def _data_type(values: list[Any]) -> str:
    populated = [value for value in values if value not in (None, "")]
    if populated and all(isinstance(value, int) and not isinstance(value, bool) for value in populated):
        return "integer"
    if populated and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in populated):
        return "number"
    return "string"


def _columns(rows: list[dict[str, Any]]) -> list[TableColumn]:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    return [
        TableColumn(
            key=key,
            label=key.replace("_", " ").title(),
            data_type=_data_type([row.get(key) for row in rows]),
        )
        for key in keys
    ]


class CsvTableExtractor(Extractor):
    """Turn one CSV file into grounded rows plus a standard table artifact."""

    descriptor = ProcessorDescriptor(
        name="toolchest.csv-table",
        version="1.0.0",
        display_name="CSV dataset table extractor",
        description=(
            "Reads a CSV header and rows, grounds every row to its source line, "
            "and returns a sortable standard table without an AI model."
        ),
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(
            media_types=["text/csv", "application/csv"],
            file_extensions=[".csv"],
            output_kinds=["text_segment", "table"],
        ),
        config_schema={
            "type": "object",
            "properties": {
                "delimiter": {"type": "string", "title": "Delimiter", "default": ","},
                "maximum_rows": {
                    "type": "integer",
                    "title": "Maximum rows",
                    "minimum": 1,
                    "default": 5000,
                },
            },
            "additionalProperties": False,
        },
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        try:
            content = base64.b64decode(request.document.content_base64 or "", validate=True)
        except ValueError as exc:
            raise ValueError("document.content_base64 is not valid base64") from exc
        delimiter = str(request.config.get("delimiter", ","))
        if len(delimiter) != 1:
            raise ValueError("delimiter must be one character")
        maximum_rows = int(request.config.get("maximum_rows", 5000))
        if maximum_rows < 1:
            raise ValueError("maximum_rows must be at least 1")

        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV file must have a header row")
        names = [str(name).strip() for name in reader.fieldnames]
        if not all(names) or len(names) != len(set(names)):
            raise ValueError("CSV column names must be non-empty and unique")

        rows: list[dict[str, Any]] = []
        segments: list[TextSegment] = []
        row_provenance: list[list[ProvenanceRef]] = []
        truncated = False
        for source_line, raw_row in enumerate(reader, start=2):
            if len(rows) >= maximum_rows:
                truncated = True
                break
            row = {
                name: _value(raw_row.get(original) or "")
                for name, original in zip(names, reader.fieldnames, strict=True)
            }
            rows.append(row)
            segment_id = f"row-{source_line}"
            segments.append(
                TextSegment(
                    id=segment_id,
                    text=json.dumps(row, ensure_ascii=False) + "\n",
                    segment_type="table_row",
                    source_origin={"source_type": "csv", "row": source_line},
                )
            )
            row_provenance.append([
                ProvenanceRef(
                    file_id=request.document.file_id,
                    segment_id=segment_id,
                    source_origin={"row": source_line},
                )
            ])

        table = TableArtifactData(
            title=f"{request.document.filename} data",
            description="CSV rows extracted directly from the source file.",
            columns=_columns(rows),
            rows=rows,
            row_provenance=row_provenance,
        )
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            artifacts=[
                Artifact(
                    id="source-table",
                    kind="table",
                    media_type="application/json",
                    standard_data=table,
                    source_origin={"source_type": "csv", "header_row": 1},
                )
            ],
            document_metadata={"row_count": len(rows), "columns": names},
            warnings=[f"Only the first {maximum_rows} rows were extracted."] if truncated else [],
        )


class CollectionTableEnricher(Enricher):
    """Merge JSON-line table rows from several extracted CSV objects."""

    descriptor = ProcessorDescriptor(
        name="toolchest.collection-table",
        version="1.0.0",
        display_name="Dataset collection table",
        description=(
            "Combines compatible rows from extracted CSV objects into one sortable "
            "collection table and identifies the source file for every row."
        ),
        kind=ProcessorKind.ENRICHER,
        capabilities=Capability(
            scope_types=["object", "folder", "collection", "root"],
            output_kinds=["table"],
        ),
        config_schema={
            "type": "object",
            "properties": {
                "maximum_rows": {
                    "type": "integer",
                    "title": "Maximum combined rows",
                    "minimum": 1,
                    "default": 10000,
                }
            },
            "additionalProperties": False,
        },
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        maximum_rows = int(request.config.get("maximum_rows", 10000))
        rows: list[dict[str, Any]] = []
        provenance: list[list[ProvenanceRef]] = []
        skipped_documents: list[str] = []

        for document in request.scope.documents:
            text = document.text or "\n".join(segment.text for segment in document.segments)
            document_rows = 0
            char_start = 0
            for line in text.splitlines(keepends=True):
                clean = line.strip()
                char_end = char_start + len(line)
                try:
                    row = json.loads(clean)
                except (json.JSONDecodeError, TypeError):
                    char_start = char_end
                    continue
                if not isinstance(row, dict):
                    char_start = char_end
                    continue
                if len(rows) >= maximum_rows:
                    break
                rows.append({"source_file": document.filename, **row})
                provenance.append([
                    ProvenanceRef(
                        file_id=document.file_id,
                        char_start=char_start,
                        char_end=char_end,
                    )
                ])
                document_rows += 1
                char_start = char_end
            if document_rows == 0:
                skipped_documents.append(document.filename)
            if len(rows) >= maximum_rows:
                break

        if not rows:
            raise ValueError(
                "No extracted CSV table rows were found in this scope. "
                "Run the CSV dataset table extractor first."
            )

        table = TableArtifactData(
            title="Combined dataset rows",
            description=(
                f"{len(rows)} grounded rows combined from "
                f"{len(request.scope.documents) - len(skipped_documents)} source file(s)."
            ),
            columns=_columns(rows),
            rows=rows,
            row_provenance=provenance,
        )
        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[
                Artifact(
                    id="collection-table",
                    kind="table",
                    media_type="application/json",
                    standard_data=table,
                )
            ],
            metadata={
                "row_count": len(rows),
                "skipped_documents": skipped_documents,
            },
            warnings=(
                ["Skipped documents without CSV row segments: " + ", ".join(skipped_documents)]
                if skipped_documents
                else []
            ),
        )
