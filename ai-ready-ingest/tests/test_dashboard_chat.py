from osii.domain.services.chat import dashboard_chat


def test_dashboard_chat_root_scope(monkeypatch, temp_osii_root, sample_osii_object):
    def fake_dashboard_search(osii_root, *, query, mode, top_k=10, scope=None):
        assert mode == "hybrid"
        assert scope["scope_type"] == "root"
        return "hybrid", [
            {
                "file_id": sample_osii_object["file_id"],
                "filename": "example.pdf",
                "source_relpath": "reports/example.pdf",
                "snippet": "Thermal calibration drift was reduced.",
                "score": 0.9,
                "match_type": "semantic",
                "chunk_id": "chunk-sha256-test123-000001",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "page": None,
                "char_start": 0,
                "char_end": 38,
                "source_origin": {
                    "grounding_type": "text_span",
                    "char_start": 0,
                    "char_end": 38,
                },
                "collections": [],
            }
        ]

    def fake_call_llm(query, scope_info, history, citations, model):
        assert query == "What does the corpus say about thermal compensation?"
        assert scope_info["type"] == "root"
        assert isinstance(citations, list)
        return "Thermal compensation is discussed in the available extracted material."

    monkeypatch.setattr("osii.domain.services.chat.dashboard_search", fake_dashboard_search)
    monkeypatch.setattr("osii.domain.services.chat._call_llm", fake_call_llm)

    result = dashboard_chat(
        temp_osii_root,
        query="What does the corpus say about thermal compensation?",
        scope={"scope_type": "root"},
        history=[],
        top_k=5,
    )

    assert "answer" in result
    assert result["answer"].startswith("Thermal compensation")
    assert "citations" in result
    assert isinstance(result["citations"], list)


def test_dashboard_chat_object_scope(monkeypatch, temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    def fake_dashboard_search(osii_root, *, query, mode, top_k=10, scope=None):
        assert scope["scope_type"] == "object"
        assert scope["file_id"] == file_id
        return "hybrid", [
            {
                "file_id": file_id,
                "filename": "example.pdf",
                "source_relpath": "reports/example.pdf",
                "snippet": "Thermal calibration drift was reduced.",
                "score": 0.9,
                "match_type": "semantic",
                "chunk_id": "chunk-sha256-test123-000001",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "page": None,
                "char_start": 0,
                "char_end": 38,
                "source_origin": {
                    "grounding_type": "text_span",
                    "char_start": 0,
                    "char_end": 38,
                },
                "collections": [],
            }
        ]

    def fake_call_llm(query, scope_info, history, citations, model):
        assert scope_info["type"] == "object"
        assert scope_info["file_id"] == file_id
        return "This appears to be a technical report about thermal calibration drift."

    monkeypatch.setattr("osii.domain.services.chat.dashboard_search", fake_dashboard_search)
    monkeypatch.setattr("osii.domain.services.chat._call_llm", fake_call_llm)

    result = dashboard_chat(
        temp_osii_root,
        query="What is this file?",
        scope={"scope_type": "object", "file_id": file_id},
        history=[],
        top_k=5,
    )

    assert "answer" in result
    assert "technical report" in result["answer"].lower()
    assert "citations" in result


def test_dashboard_chat_collection_scope(monkeypatch, temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="thermal-set",
        description="test collection",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    def fake_dashboard_search(osii_root, *, query, mode, top_k=10, scope=None):
        assert scope["scope_type"] == "collection"
        assert scope["collection_id"] == collection["id"]
        return "hybrid", [
            {
                "file_id": file_id,
                "filename": "example.pdf",
                "source_relpath": "reports/example.pdf",
                "snippet": "Thermal calibration drift was reduced.",
                "score": 0.9,
                "match_type": "semantic",
                "chunk_id": "chunk-sha256-test123-000001",
                "chunk_method": "paragraph",
                "chunk_index": 1,
                "page": None,
                "char_start": 0,
                "char_end": 38,
                "source_origin": {
                    "grounding_type": "text_span",
                    "char_start": 0,
                    "char_end": 38,
                },
                "collections": [{"id": collection["id"], "name": collection["name"], "kind": collection["kind"]}],
            }
        ]

    def fake_call_llm(query, scope_info, history, citations, model):
        assert scope_info["type"] == "collection"
        assert scope_info["collection_id"] == collection["id"]
        return "The collection contains material about thermal calibration drift."

    monkeypatch.setattr("osii.domain.services.chat.dashboard_search", fake_dashboard_search)
    monkeypatch.setattr("osii.domain.services.chat._call_llm", fake_call_llm)

    result = dashboard_chat(
        temp_osii_root,
        query="What is in this collection?",
        scope={"scope_type": "collection", "collection_id": collection["id"]},
        history=[],
        top_k=5,
    )

    assert "answer" in result
    assert "collection" in result["answer"].lower()


def test_dashboard_chat_missing_query(temp_osii_root):
    try:
        dashboard_chat(
            temp_osii_root,
            query="",
            scope={"scope_type": "root"},
            history=[],
            top_k=5,
        )
        assert False, "Expected ValueError for empty query"
    except ValueError as exc:
        assert "query is required" in str(exc).lower()
