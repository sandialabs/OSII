from osii.domain.processing.scope_batches import (
    BatchLimits,
    input_batches,
    normalize_result,
)
import pytest


def test_whole_corpus_has_no_document_limit_and_late_text_is_retained():
    texts = {str(i): ("prefix " + str(i) + " ") * 400 for i in range(1201)}
    texts["long"] = "x" * 3000 + " final marker"
    rows = list(
        input_batches(
            ({"file_id": key, "text": text} for key, text in texts.items()),
            BatchLimits(1000, 8),
        )
    )
    reconstructed = {key: "" for key in texts}
    for batch in rows:
        assert len(batch) <= 8 and sum(len(row["text"]) for row in batch) <= 1000
        assert len({row["file_id"] for row in batch}) == len(batch)
        for row in batch:
            reconstructed[row["file_id"]] += row["text"]
    assert reconstructed == texts


def test_citation_offsets_are_translated_and_invalid_references_rejected():
    rows = [{"file_id": "a", "text": "source", "char_start": 100}]
    result = normalize_result(
        {
            "markdown": "summary",
            "citations": [{"file_id": "a", "char_start": 1, "char_end": 4}],
        },
        rows,
    )
    assert (
        result["citations"][0]["char_start"] == 101
        and result["citations"][0]["char_end"] == 104
    )
    with pytest.raises(ValueError):
        normalize_result(
            {"markdown": "bad", "citations": [{"file_id": "outside"}]}, rows
        )
    with pytest.raises(ValueError):
        normalize_result(
            {"markdown": "bad", "citations": [{"file_id": "a", "char_end": 7}]}, rows
        )


def test_processor_reported_truncation_is_not_accepted_as_complete():
    with pytest.raises(ValueError, match="truncated"):
        normalize_result(
            {"markdown": "partial", "metadata": {"input_truncated": True}},
            [{"file_id": "a", "text": "full source"}],
        )
