from osii.domain.services.search import _group_results_by_file


def test_group_results_by_file_keeps_best_hit():
    results = [
        {
            "file_id": "sha256-a",
            "source_relpath": "a.pdf",
            "score": 1.0,
            "chunk_id": "chunk-a-1",
        },
        {
            "file_id": "sha256-a",
            "source_relpath": "a.pdf",
            "score": 5.0,
            "chunk_id": "chunk-a-2",
        },
        {
            "file_id": "sha256-b",
            "source_relpath": "b.pdf",
            "score": 3.0,
            "chunk_id": "chunk-b-1",
        },
    ]

    grouped = _group_results_by_file(results, top_k=10)

    assert len(grouped) == 2
    assert grouped[0]["file_id"] == "sha256-a"
    assert grouped[0]["chunk_id"] == "chunk-a-2"
    assert grouped[1]["file_id"] == "sha256-b"