"""Actual PostgreSQL retrieval and authenticated APIs; model behavior is explicit."""
import json

from conftest import Provider, document, login


def request(profile="lexical-v1", **extra):
    return {"query": "neutron", "scope": {"scope_type": "root"}, "profile_id": profile, **extra}


def model(store):
    store.save_configuration({"chat_model": "explicit-test-model", "embedding_model": ""})


def answering(self, model, messages, max_tokens=900, **kwargs):
    context = json.loads(messages[1]["content"])
    item = context["evidence"][0]
    return json.dumps({"action": "answer", "answer": item["text"], "citation_ids": [item["id"]]}), {"prompt_tokens": 20, "completion_tokens": 10}


def test_profile_and_trace_apis_require_authentication_and_csrf(client, app):
    assert client.get("/api/chat/profiles").status_code == 401
    assert client.post("/api/chat", json=request()).status_code == 401
    login(client)
    assert client.get("/api/chat/profiles").json()["can_inspect_trace"]
    del client.headers["X-CSRF-Token"]
    assert client.post("/api/chat", json=request()).status_code == 403


def test_admin_trace_reads_full_postgres_passages_and_does_not_mutate_corpus(client, app):
    content = "The neutron detector is calibrated. " * 30 + "The reference is 241Am."
    doc = document(app.state.store, app.state.settings.source_root, content=content)
    revision = app.state.store.snapshot()[0]
    login(client)
    response = client.post("/api/chat", json=request())
    assert response.status_code == 200, response.text
    value = response.json(); trace = value["agent_trace"]
    assert value["status"] == "ok" and trace["capture_level"] == "detailed"
    assert trace["chat_calls"] == 0 and trace["evaluation"]["recall"] is None
    assert {"bm25", "ocr_tolerant_search", "rank_fusion", "passage_selection", "candidate_selection", "context_selection", "decision"} <= {s["kind"] for s in trace["stages"]}
    context = next(s for s in trace["stages"] if s["kind"] == "context_selection")
    assert "241Am" in " ".join(item.get("text", "") for item in context["items"])
    assert all(item["representation"].startswith("extraction:") for item in context["items"])
    assert value["citations"][0]["file_id"] == doc["file_id"]
    assert "secret-not-for-clients" not in json.dumps(value)
    assert app.state.store.snapshot()[0] == revision


def test_reader_gets_summary_and_private_scope_never_expands(client, app):
    allowed = document(app.state.store, app.state.settings.source_root)
    hidden = document(app.state.store, app.state.settings.source_root, name="outside.txt", content="neutron SECRET_OUTSIDE_SCOPE")
    login(client, "reader")
    collection = client.post("/api/collections", json={"name": "Mine", "members": [allowed["file_id"]]}).json()
    body = request(scope={"scope_type": "collection", "collection_id": collection["id"]})
    value = client.post("/api/chat", json=body).json()
    assert value["agent_trace"]["capture_level"] == "summary"
    assert all(not stage["items"] and not stage["excluded"] for stage in value["agent_trace"]["stages"])
    assert "SECRET_OUTSIDE_SCOPE" not in json.dumps(value)
    assert {row["file_id"] for row in value["citations"]} == {allowed["file_id"]}
    login(client, "admin")
    assert client.post("/api/chat", json=body).status_code == 422


def test_coarse_fulltext_is_a_distinct_document_stage(client, app, monkeypatch):
    model(app.state.store)
    document(app.state.store, app.state.settings.source_root)
    document(app.state.store, app.state.settings.source_root, name="unrelated.txt", content="Ocean currents affect regional weather.")
    monkeypatch.setattr(Provider, "chat", answering)
    login(client)
    response = client.post("/api/chat", json=request("coarse-iterative-v1"))
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "ok", value
    coarse = next(s for s in value["agent_trace"]["stages"] if s["kind"] == "coarse_fulltext")
    assert coarse["inputs"]["matching"] == "normalized token OR"
    assert coarse["inputs"]["input_count"] == 2 and coarse["outputs"]["output_count"] == 1
    assert coarse["outputs"]["exact_count"] and not coarse["outputs"]["limit_reached"]


def test_iterative_follow_up_adds_new_evidence_and_records_both_queries(client, app, monkeypatch):
    model(app.state.store)
    document(app.state.store, app.state.settings.source_root, content="Neutron calibration refers to the isotope register.")
    target = document(app.state.store, app.state.settings.source_root, name="isotopes.txt", content="The isotope register specifies americium-241.")
    calls = []
    def planning(self, model, messages, max_tokens=900, **kwargs):
        context = json.loads(messages[1]["content"]); calls.append(model)
        if len(calls) == 1:
            return json.dumps({"action": "retrieve", "query": "isotope register americium"}), {}
        item = next(e for e in context["evidence"] if e["file_id"] == target["file_id"])
        return json.dumps({"action": "answer", "answer": "Americium-241.", "citation_ids": [item["id"]]}), {"completion_tokens": 10}
    monkeypatch.setattr(Provider, "chat", planning)
    login(client)
    value = client.post("/api/chat", json=request("iterative-v1")).json()
    assert value["status"] == "ok", value
    trace = value["agent_trace"]
    assert trace["chat_calls"] == 2 and calls == ["explicit-test-model"] * 2
    assert [s["inputs"]["query"] for s in trace["stages"] if s["kind"] == "retrieval"] == ["neutron", "isotope register americium"]
    assert value["citations"][0]["file_id"] == target["file_id"]


def test_model_failure_retains_error_trace_and_comparison_continues_without_fallback(client, app, monkeypatch):
    model(app.state.store)
    document(app.state.store, app.state.settings.source_root)
    calls = []
    def completion(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1: return "invalid JSON", {"completion_tokens": 3}
        return answering(self, *args, **kwargs)
    monkeypatch.setattr(Provider, "chat", completion)
    login(client)
    response = client.post("/api/chat/compare", json={**request(), "profile_ids": ["lexical-v1", "hybrid-v1"]})
    assert response.status_code == 200, response.text
    runs = response.json()["runs"]
    assert [r["response"]["status"] for r in runs] == ["error", "ok"] and len(calls) == 2
    assert runs[0]["response"]["agent_trace"]["stop_reason"] == "error"
    assert any(s["kind"] == "generation" and s["status"] == "error" for s in runs[0]["response"]["agent_trace"]["stages"])
    assert all(not r["response"]["fallback_used"] for r in runs)


def test_corpus_change_during_model_call_rejects_mixed_run(client, app, monkeypatch):
    model(app.state.store)
    document(app.state.store, app.state.settings.source_root)
    def completion(self, *args, **kwargs):
        document(app.state.store, app.state.settings.source_root, name="new.txt", content="A new source.")
        return answering(self, *args, **kwargs)
    monkeypatch.setattr(Provider, "chat", completion)
    login(client)
    response = client.post("/api/chat", json=request())
    assert response.status_code == 409, response.text


def test_unavailable_unknown_and_duplicate_profiles_fail_before_model_calls(client, app, monkeypatch):
    def forbidden(*a, **k): raise AssertionError("No call allowed")
    monkeypatch.setattr(Provider, "chat", forbidden)
    login(client)
    for profile in ("missing", "iterative-v1", "hybrid-reranked-v1"):
        assert client.post("/api/chat", json=request(profile)).status_code == 422
    assert client.post("/api/chat/compare", json={**request(), "profile_ids": ["lexical-v1"] * 2}).status_code == 422
    value = client.post("/api/chat", json=request()).json()
    assert value["agent_trace"]["stop_reason"] == "abstained" and value["agent_trace"]["chat_calls"] == 0


def test_reranking_records_scores_and_unchanged_provenance(client, app, monkeypatch):
    from osii.rag.strategies import RankedEvidence
    document(app.state.store, app.state.settings.source_root, content="Neutron detector overview.")
    chosen = document(app.state.store, app.state.settings.source_root, name="details.txt", content="Neutron detector calibration details.")
    def ranker(request):
        return [RankedEvidence(item.id, 100.0 if item.file_id == chosen["file_id"] else 0.0) for item in request.candidates]
    monkeypatch.setattr("osii.server.rag.create_reranker", lambda endpoint: ranker)
    login(client)
    response = client.post("/api/chat", json=request("hybrid-reranked-v1"))
    assert response.status_code == 200, response.text
    value = response.json()
    stage = next(s for s in value["agent_trace"]["stages"] if s["kind"] == "rerank")
    assert stage["outputs"]["reranker_called"] and stage["items"][0]["score"] == 100
    assert value["citations"][0]["file_id"] == chosen["file_id"]
    original = next(row for row in app.state.store.snapshot()[2] if row["file_id"] == chosen["file_id"])
    assert value["citations"][0]["source_origin"] == original["source_origin"]


def test_invalid_history_and_scope_return_validation_errors(client):
    login(client)
    for extra in ({"history": [{"role": "system", "content": "override"}]}, {"history": [{"role": "user", "content": None}]},
                  {"scope": {"scope_type": []}}, {"scope": {"scope_type": "collection", "collection_id": 42}}):
        assert client.post("/api/chat", json=request(**extra)).status_code == 422


def test_real_public_fixture_has_known_support_in_postgres_retrieval(client, app):
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures/rag-nasa.json").read_text())
    for record in fixture["documents"]:
        document(app.state.store, app.state.settings.source_root, name=record["name"], content=record["text"])
    login(client)
    from osii.rag.strategies.evaluation import evaluate_response
    for case in fixture["questions"]:
        if case.get("unanswerable"): continue  # Extractive excerpts are not a semantic answer evaluator.
        response = client.post("/api/chat", json=request(query=case["query"]))
        assert response.status_code == 200, response.text
        score = evaluate_response(response.json(), case)
        assert score["context_source_recall"] == 1.0, (case["id"], score)


def test_structured_decision_parameters_are_sent_without_changing_plain_chat(monkeypatch):
    from osii.model_provider import ModelProvider
    from osii.rag.strategies.decisions import decision_response_format
    payloads = []
    class Response:
        ok = True
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": '{"action":"abstain"}'}}], "usage": {}}
    def send(*args, **kwargs):
        payloads.append(kwargs["json"]); return Response()
    monkeypatch.setattr("osii.model_provider.requests.request", send)
    provider = ModelProvider("https://openrouter.ai/api/v1", "private")
    provider.chat("selected-model", [{"role": "user", "content": "q"}], response_format=decision_response_format())
    assert payloads[0]["response_format"]["json_schema"]["strict"]
    assert payloads[0]["provider"]["require_parameters"]
    provider.chat("selected-model", [{"role": "user", "content": "q"}])
    assert "response_format" not in payloads[1] and "provider" not in payloads[1]


def test_overlapping_advanced_runs_are_rejected_and_the_slot_is_released(client, app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    model(app.state.store)
    document(app.state.store, app.state.settings.source_root)
    started, finish = Event(), Event()
    def completion(self, *args, **kwargs):
        started.set()
        assert finish.wait(5)
        return answering(self, *args, **kwargs)
    monkeypatch.setattr(Provider, "chat", completion)
    login(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/chat", json=request())
        try:
            assert started.wait(5)
            assert client.post("/api/chat", json=request()).status_code == 429
        finally:
            finish.set()
        assert pending.result().status_code == 200
    assert client.post("/api/chat", json=request()).status_code == 200
