from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

from osii_processor_sdk import (
    DocumentInput,
    EnrichmentRequest,
    ExtractionRequest,
    ScopeInput,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_csv_extractor_and_collection_enricher_return_standard_tables():
    processors = _load_module(
        "osii_dataset_processors_test",
        REPOSITORY_ROOT / "examples" / "tabular-dataset-processors" / "dataset_processors.py",
    )
    source = b"length,width,target_class\n5.1,3.5,0\n4.9,3.0,0\n"
    extraction = processors.CsvTableExtractor().extract(
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

    enrichment = processors.CollectionTableEnricher().enrich(
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


def test_example_dataset_archive_is_safely_unpackable(tmp_path: Path, monkeypatch):
    importer = _load_module(
        "osii_import_example_data_test",
        REPOSITORY_ROOT / "scripts" / "import_example_data.py",
    )
    dataset = importer.DatasetExport(
        slug="tiny",
        display_name="Tiny dataset",
        description="A test dataset.",
        feature_names=["measurement"],
        target_name="target_class",
        target_names=["first", "second"],
        rows=[[1.5], [2.5]],
        targets=[0, 1],
    )
    archive = tmp_path / "tiny.zip"
    importer.build_dataset_archive(dataset, archive)
    written = importer.unpack_dataset_archive(archive, tmp_path / "output")

    csv_paths = sorted(path for path in written if path.suffix == ".csv")
    assert [path.name for path in csv_paths] == ["first.csv", "second.csv"]
    metadata = json.loads((tmp_path / "output" / "tiny" / "dataset.json").read_text())
    assert metadata["row_count"] == 2

    configured = tmp_path / "configured-source"
    monkeypatch.setenv("OSII_SOURCE_DIR", str(configured))
    assert importer.configured_destination() == configured
