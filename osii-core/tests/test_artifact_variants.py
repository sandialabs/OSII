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