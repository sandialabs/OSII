from osii.domain.artifacts.object_processing import get_object_processing_metadata


def test_object_processing_metadata_default(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    data = get_object_processing_metadata(temp_osii_root, file_id)
    assert data is not None
    assert "extractor" in data
    assert "synthesizer" in data
    assert "canonical_text_path" in data
    assert "editable_text_path" in data
    assert "has_editable_text" in data
    assert "capabilities" in data
    assert data["canonical_text_path"] == f"objects/{file_id}/text.txt"
    assert data["has_editable_text"] is False
    assert data["capabilities"]["supports_markdown_render"] is False