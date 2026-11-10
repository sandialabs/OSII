"""Deterministic pilot checks over recorded outputs, separate from execution."""
from __future__ import annotations


def evaluate_response(response: dict, case: dict) -> dict:
    """Supporting-source coverage and literal answer checks, not semantic judging.

    Labels may be incomplete. Recall is against those labels only. Literal checks
    cannot establish entailment, correct units, or absence of extra false claims.
    """
    expected = set(case.get("expected_sources", []))
    trace = response.get("agent_trace") or {}
    context_sources = {item.get("source_relpath") for stage in trace.get("stages", [])
                       if stage["kind"] == "context_selection" for item in stage.get("items", [])}
    cited = {item.get("source_relpath") for item in response.get("citations", [])}
    answer = response.get("answer", "").casefold()
    checks = [any(str(value).casefold() in answer for value in alternatives)
              for alternatives in case.get("answer_contains", [])]
    abstained = trace.get("stop_reason") == "abstained"
    return {"id": case.get("id"), "category": case.get("category"), "status": response.get("status"),
            "context_source_recall": len(expected & context_sources) / len(expected) if expected else None,
            "citation_source_recall": len(expected & cited) / len(expected) if expected else None,
            "answer_checks_passed": all(checks) if checks else None,
            "appropriate_abstention": abstained if case.get("unanswerable") else None,
            "chat_calls": trace.get("chat_calls"), "stop_reason": trace.get("stop_reason"),
            "elapsed_seconds": trace.get("elapsed_seconds"), "answer": response.get("answer"),
            "error": response.get("error")}
