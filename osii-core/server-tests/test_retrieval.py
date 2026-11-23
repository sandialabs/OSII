import pytest
from osii.search.engine import RetrievalEngine, normalize, tokens


def row(text, n=0, **values):
    return {"file_id": str(n), "chunk_id": str(n), "text": text, "char_start": 0, "char_end": len(text), **values}


@pytest.mark.parametrize("query,ocr", [
    ("neutron", "neut-\nron"), ("thermal", "therrnal"),
    ("123456", "report 123456"), ("café", "CAFÉ"),
    ("241Am", "isotope 241Am"), ("calibration", "caIibration"),
    ("detector", "detecfor"), ("response", "responsc"),
])
def test_ocr_and_identifier_recall(query, ocr):
    evidence = row(ocr, 1)
    result, channels = RetrievalEngine().search([row("unrelated ocean document"), evidence], query, revision=1)
    assert result and result[0]["file_id"] == "1"
    assert result[0]["text"] == ocr


def test_scope_and_model_revision_and_empty_results():
    engine = RetrievalEngine()
    result, _ = engine.search([row("thermal detector")], "pineapple", revision=1)
    assert result == []
    result, channels = engine.search([row("unrelated words", embedding=[1, 0], embedding_model="old")],
        "neutron", revision=2, query_vector=[1, 0], embedding_model="new", mode="semantic")
    assert result == [] and channels == []
    result, channels = engine.search([row("unrelated words", embedding=[1, 0], embedding_model="new")],
        "neutron", revision=3, query_vector=[1, 0], embedding_model="new", mode="semantic")
    assert len(result) == 1 and channels == ["semantic"]


def test_normalization_never_changes_numeric_identity():
    assert tokens("report 123456 241Am café") == ["report", "123456", "241am", "café"]
    assert normalize("neu-\ntron") == "neutron"
    result, _ = RetrievalEngine().search([row("report 123457")], "123456", revision=1)
    assert result == []
