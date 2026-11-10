from osii.domain.artifacts.enrichment_artifacts import write_object_enrichment_variant
from osii.domain.artifacts.synth_artifacts import write_object_synthesis_variant


def test_write_object_synthesis_variant(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    result = write_object_synthesis_variant(
        temp_osii_root,
        file_id,
        method="stats-summary-v1",
        text="A concise non-LLM summary.",
        metadata={"family": "statistics"},
    )

    assert result["file_id"] == file_id
    assert result["method"] == "stats-summary-v1"

    text_path = temp_osii_root / result["text_path"]
    meta_path = temp_osii_root / result["metadata_path"]

    assert text_path.exists()
    assert meta_path.exists()


def test_shared_reader_honors_committed_product_when_compatibility_file_is_missing(temp_osii_root, sample_osii_object):
    import json
    from osii.domain.artifacts.products import read_product
    from osii.domain.read.sidecar import SidecarLibraryReader
    from osii.domain.artifacts.read_enrichments import get_object_enrichment_payload

    file_id = sample_osii_object["file_id"]
    payload = {"artifact_type": "wiki_markdown", "title": "Detector", "markdown": "# Detector", "citations": []}
    result = write_object_enrichment_variant(temp_osii_root, file_id,
        kind="wiki", method="test", payload=payload)
    path = temp_osii_root / result["data_path"]
    assert read_product(path)["data"] == payload
    path.unlink()  # Simulate interruption before the compatibility view is repaired.
    reader = SidecarLibraryReader(temp_osii_root, product_reader=read_product)
    listed = reader.list_artifacts(file_id)
    artifact = next(row for row in listed.items if row.kind == "wiki_markdown")
    assert json.loads(reader.get_artifact(file_id, artifact.artifact_id).data) == payload
    assert get_object_enrichment_payload(temp_osii_root, file_id, path.name)["data"] == payload
    assert not path.exists()  # A read never repairs or overwrites canonical data.


def test_write_object_enrichment_variant(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    result = write_object_enrichment_variant(
        temp_osii_root,
        file_id,
        kind="keywords",
        method="tfidf-v1",
        payload={"keywords": ["calibration", "drift", "thermal"]},
        metadata={"family": "statistics"},
    )

    assert result["file_id"] == file_id
    assert result["kind"] == "keywords"
    assert result["method"] == "tfidf-v1"

    data_path = temp_osii_root / result["data_path"]
    meta_path = temp_osii_root / result["metadata_path"]

    assert data_path.exists()
    assert meta_path.exists()
