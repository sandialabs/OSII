from osii.domain.artifacts.text_spans import get_text_by_span, get_text_context_by_span


def test_get_text_by_span(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    text = get_text_by_span(
        temp_osii_root,
        file_id,
        char_start=0,
        char_end=10,
    )
    assert text is not None
    assert len(text) == 10


def test_get_text_context_by_span(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    result = get_text_context_by_span(
        temp_osii_root,
        file_id,
        char_start=0,
        char_end=10,
        context_chars=5,
    )
    assert result is not None
    assert result["file_id"] == file_id
    assert "match_text" in result
    assert "before_text" in result
    assert "after_text" in result