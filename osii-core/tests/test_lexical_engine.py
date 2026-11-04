"""Exercise the real BM25 library, not a mocked search result."""
from pathlib import Path

import bm25s
import pytest

from osii.search import lexical


@pytest.fixture
def index(monkeypatch):
    rows = [
        {"file_id": "ocean", "text": "ocean temperature salinity"},
        {"file_id": "detector", "text": "thermal neutron detector response"},
        {"file_id": "other", "text": "historical annual financial accounts"},
    ]
    retriever = bm25s.BM25()
    retriever.index([lexical.tokenize(row["text"]) for row in rows], show_progress=False)
    monkeypatch.setattr(lexical, "load_bm25_index", lambda _: (retriever, rows))
    return rows


def test_real_library_document_ids_and_scores(index):
    results = lexical.lexical_search_chunks(Path("unused"), "neutron", top_k=3)
    assert [row["file_id"] for row in results] == ["detector"]
    assert results[0]["score"] > 0
    assert "score" not in index[1]


def test_zero_match_does_not_return_unrelated_documents(index):
    assert lexical.lexical_search_chunks(Path("unused"), "pineapple") == []


@pytest.mark.parametrize("query,limit", [("", 10), ("neutron", 0), ("neutron", -1)])
def test_empty_request(index, query, limit):
    assert lexical.lexical_search_chunks(Path("unused"), query, limit) == []
