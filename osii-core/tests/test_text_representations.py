from osii.domain.artifacts.edited_text import put_edited_text_segments
from osii.domain.artifacts.text_representations import (
    get_preferred_text_representation,
    list_text_representations,
)


def test_list_text_representations_canonical_only(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    reps = list_text_representations(temp_osii_root, file_id)
    assert reps is not None
    assert len(reps) == 2

    canonical = next(item for item in reps if item["name"] == "canonical")
    edited = next(item for item in reps if item["name"] == "edited")

    assert canonical["exists"] is True
    assert canonical["preferred"] is True
    assert edited["exists"] is False
    assert edited["preferred"] is False


def test_preferred_text_is_edited_when_present(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    put_edited_text_segments(
        temp_osii_root,
        file_id,
        [
            {
                "id": "seg-000001",
                "text": "Corrected OCR text.",
            }
        ],
    )

    preferred = get_preferred_text_representation(temp_osii_root, file_id)
    assert preferred is not None
    assert preferred["name"] == "edited"
    assert preferred["kind"] == "edited_text"
    assert "Corrected OCR text." in preferred["text"]