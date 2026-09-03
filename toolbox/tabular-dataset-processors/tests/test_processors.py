from __future__ import annotations

import base64

from tabular_processors.processors import CollectionTableEnricher, CsvTableExtractor
from osii_processor_sdk import (
    DocumentInput,
    EnrichmentRequest,
    ExtractionRequest,
    ScopeInput,
)


def test_csv_extractor_and_collection_enricher_return_standard_tables() -> None:
    source = b"length,width,target_class\n5.1,3.5,0\n4.9,3.0,0\n"
    extraction = CsvTableExtractor().extract(
        ExtractionRequest(
            request_id="extract-test",
            document=DocumentInput(
                file_id="sha256-test",
                filename="setosa.csv",
                media_type="text/csv",
                content_base64=base64.b64encode(source).decode("ascii"),
            ),
        )
    )

    table = extraction.artifacts[0].standard_data
    assert table.artifact_type == "table"
    assert len(extraction.segments) == 2
    assert table.rows[0] == {"length": 5.1, "width": 3.5, "target_class": 0}
    assert table.row_provenance[0][0].source_origin == {"row": 2}

    enrichment = CollectionTableEnricher().enrich(
        EnrichmentRequest(
            request_id="enrich-test",
            scope=ScopeInput(
                scope_type="collection",
                scope_id="iris",
                documents=[
                    DocumentInput(
                        file_id="sha256-test",
                        filename="setosa.csv",
                        text="".join(segment.text for segment in extraction.segments),
                    )
                ],
            ),
        )
    )
    combined = enrichment.artifacts[0].standard_data
    assert combined.artifact_type == "table"
    assert combined.rows[0]["source_file"] == "setosa.csv"
    assert combined.row_provenance[1][0].char_start > 0
