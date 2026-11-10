import json

import pytest

from osii.rag.strategies import Decision, Evidence, Question
from osii.rag.strategies.experiments import run_profile
from osii.rag.strategies.profiles import get_profile
from osii.rag.strategies.tracing import AgentTrace


def test_trace_records_nested_failures_and_bounded_payloads_without_changing_sources():
    trace = AgentTrace("test", item_limit=1)
    rows = [{"id": "a", "text": "x" * 5000, "source_origin": {"page": 2}}, {"id": "b"}]
    with pytest.raises(RuntimeError):
        with trace.span("run", "Run"):
            with trace.span("search", "Search", query="private question") as stage:
                stage.items = rows
                stage.outputs["output_count"] = 2
                raise RuntimeError("not captured")
    result = trace.export()
    assert result["stages"][1]["parent_id"] == result["stages"][0]["id"]
    assert all(stage["status"] == "error" for stage in result["stages"])
    assert stage.outputs["items_omitted"] == 1 and stage.items[0]["text_truncated"]
    assert len(rows[0]["text"]) == 5000
    stage.items[0]["source_origin"]["page"] = 9
    assert rows[0]["source_origin"]["page"] == 2
    summary = trace.export(detailed=False)
    assert "private question" not in json.dumps(summary)
    assert all(not stage["items"] for stage in summary["stages"])
    assert not trace.parents


def test_context_budget_exclusions_are_visible_and_original_evidence_remains_intact():
    trace = AgentTrace("lexical-v1")
    passages = [Evidence("a", "file-a", "a" * 15000), Evidence("b", "file-b", "b" * 15000)]
    result = run_profile(Question("q"), get_profile("lexical-v1"), retrieve=lambda *a, **k: passages,
                         decide=lambda ctx: Decision("abstain"), trace=trace)
    stage = next(s for s in trace.stages if s.kind == "context_selection")
    assert len(result.result.evidence) == 1 and result.result.evidence[0].text == passages[0].text
    assert stage.excluded == [{"id": "b", "reason": "context count or character budget"}]
    assert stage.items[0]["text_characters"] == 15000


def test_evaluation_counts_unique_labeled_sources_and_does_not_invent_recall():
    from osii.rag.strategies.evaluation import evaluate_response
    response = {"status": "ok", "answer": "88", "citations": [{"source_relpath": "a"}],
                "agent_trace": {"stop_reason": "answered", "stages": [{"kind": "context_selection", "items": [
                    {"source_relpath": "a"}, {"source_relpath": "a"}, {"source_relpath": "unlabeled"}]}]}}
    result = evaluate_response(response, {"expected_sources": ["a", "b"], "answer_contains": [["88"]]})
    assert result["context_source_recall"] == result["citation_source_recall"] == .5
    assert result["answer_checks_passed"]
    result = evaluate_response({"agent_trace": {"stop_reason": "abstained"}}, {"unanswerable": True})
    assert result["context_source_recall"] is None and result["appropriate_abstention"]
