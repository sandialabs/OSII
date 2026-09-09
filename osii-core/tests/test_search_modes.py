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
                "source_segment_ids": ["seg-000001"],
                "source_pages": [1],
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
    assert results[0]["page"] == 1
    assert results[0]["segment_id"] == "seg-000001"


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


def test_dashboard_search_suppresses_nearly_duplicate_overlapping_chunks(
    monkeypatch,
    temp_osii_root,
):
    def fake_lexical_search_chunks(osii_root, query, top_k=10):
        base = {
            "file_id": "sha256-test123",
            "source_relpath": "reports/example.pdf",
            "chunk_method": "sentence_window",
            "source_text_representation": "canonical",
            "source_text_kind": "canonical_extracted_text",
        }
        return [
            {**base, "chunk_id": "chunk-1", "chunk_index": 1, "char_start": 0, "char_end": 100, "score": 3.0},
            {**base, "chunk_id": "chunk-2", "chunk_index": 2, "char_start": 20, "char_end": 120, "score": 2.9},
            {**base, "chunk_id": "chunk-3", "chunk_index": 3, "char_start": 120, "char_end": 180, "score": 2.0},
        ]

    monkeypatch.setattr(
        "osii.domain.services.search.lexical_search_chunks",
        fake_lexical_search_chunks,
    )
    _, results = dashboard_search(
        temp_osii_root,
        query="thermal",
        mode="lexical",
        top_k=3,
        scope={"scope_type": "root"},
    )

    assert [result["chunk_id"] for result in results] == ["chunk-1", "chunk-3"]
