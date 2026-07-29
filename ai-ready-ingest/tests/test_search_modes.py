from osii.domain.services.search import dashboard_search


def test_dashboard_search_lexical_mode(monkeypatch, temp_osii_root):
    def fake_lexical_search_chunks(osii_root, query, top_k=10):
        return [
            {
                "chunk_id": "chunk-1",
                "file_id": "sha256-test123",
                "source_relpath": "reports/example.pdf",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "char_start": 0,
                "char_end": 20,
                "source_text_representation": "canonical",
                "source_text_kind": "canonical_extracted_text",
                "score": 2.5,
            }
        ]

    monkeypatch.setattr("osii.domain.services.search.lexical_search_chunks", fake_lexical_search_chunks)

    retrieval_mode, results = dashboard_search(
        temp_osii_root,
        query="thermal",
        mode="lexical",
        top_k=5,
        scope={"scope_type": "root"},
    )

    assert retrieval_mode == "lexical"
    assert len(results) == 1
    assert results[0]["match_type"] == "lexical"
    assert results[0]["chunk_id"] == "chunk-1"


def test_dashboard_search_hybrid_mode(monkeypatch, temp_osii_root):
    def fake_lexical_search_chunks(osii_root, query, top_k=10):
        return [
            {
                "chunk_id": "chunk-1",
                "file_id": "sha256-test123",
                "source_relpath": "reports/example.pdf",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "char_start": 0,
                "char_end": 20,
                "source_text_representation": "canonical",
                "source_text_kind": "canonical_extracted_text",
                "score": 2.5,
            }
        ]

    def fake_search_segments(osii_root, query, top_k=10, model=None):
        return [
            {
                "chunk_id": "chunk-1",
                "file_id": "sha256-test123",
                "source_relpath": "reports/example.pdf",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "char_start": 0,
                "char_end": 20,
                "source_text_representation": "canonical",
                "source_text_kind": "canonical_extracted_text",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr("osii.domain.services.search.lexical_search_chunks", fake_lexical_search_chunks)
    monkeypatch.setattr("osii.domain.services.search.search_segments", fake_search_segments)

    retrieval_mode, results = dashboard_search(
        temp_osii_root,
        query="thermal",
        mode="hybrid",
        top_k=5,
        scope={"scope_type": "root"},
    )

    assert retrieval_mode == "hybrid"
    assert len(results) == 1
    assert results[0]["match_type"] == "hybrid"
    assert results[0]["chunk_id"] == "chunk-1"
