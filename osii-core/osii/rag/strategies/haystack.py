"""Optional Haystack pipelines over explicit OSII retrieval and decision ports.

No document store, tools, model SDK, or corpus is created by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import islice
import os
import time

# Experiments are opt-in; framework telemetry is not part of the data path.
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")
from haystack import Pipeline, component
from haystack.core.errors import PipelineRuntimeError
from haystack.components.joiners import BranchJoiner

from .contracts import Context, Decider, Decision, Evidence, Limits, Question, Result, Retriever, Step, StrategyError


@dataclass
class _State:
    question: Question
    limits: Limits
    strategy: str
    started: float = field(default_factory=time.monotonic)
    queries: list[str] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    pending: str = ""
    model_calls: int = 0
    decision: Decision | None = None
    stop: str = ""
    revision: str | None = None

    def expired(self) -> bool:
        return time.monotonic() - self.started >= self.limits.deadline_seconds


@component
class _Retrieve:
    def __init__(self, retrieve: Retriever):
        self.retrieve = retrieve

    @component.output_types(state=_State)
    def run(self, state: _State) -> dict:
        if state.expired():
            state.stop = "deadline"
        if state.stop:
            return {"state": state}
        query = state.pending or state.question.text
        if len(state.queries) >= state.limits.max_retrievals:
            state.stop = "retrieval_limit"
            return {"state": state}
        if query.casefold().strip() in {q.casefold().strip() for q in state.queries}:
            state.stop = "repeated_query"
            return {"state": state}
        state.queries.append(query)
        added = []
        remaining = state.limits.max_context_chars - sum(len(e.text) for e in state.evidence.values())
        for evidence in islice(self.retrieve(query, top_k=state.limits.top_k), state.limits.top_k):
            if not isinstance(evidence, Evidence):
                raise StrategyError("Retriever must return Evidence records")
            if evidence.corpus_revision is not None:
                if state.revision is not None and state.revision != evidence.corpus_revision:
                    raise StrategyError("Corpus changed during retrieval; retry against one revision")
                state.revision = evidence.corpus_revision
            previous = state.evidence.get(evidence.id)
            if previous is not None:
                if previous != evidence:
                    raise StrategyError("An evidence ID changed within this experiment")
                continue
            if len(state.evidence) >= state.limits.max_evidence or len(evidence.text) > remaining:
                continue  # Keep original text and offsets intact; never silently truncate evidence.
            state.evidence[evidence.id] = evidence
            remaining -= len(evidence.text)
            added.append(evidence.id)
        state.steps.append(Step(query, tuple(added), "retrieved"))
        return {"state": state}


@component
class _Decide:
    def __init__(self, decide: Decider):
        self.decide = decide

    @component.output_types(state=_State)
    def run(self, state: _State) -> dict:
        if state.expired():
            state.stop = "deadline"
        if state.stop:
            return {"state": state}
        if state.model_calls >= state.limits.max_model_calls:
            state.stop = "model_call_limit"
            return {"state": state}
        state.model_calls += 1
        context = Context(state.question, tuple(state.evidence.values()), tuple(state.queries),
            len(state.queries) < state.limits.max_retrievals and state.model_calls < state.limits.max_model_calls,
            state.limits.max_output_tokens)
        decision = self.decide(context)
        if not isinstance(decision, Decision):
            raise StrategyError("Decider must return a Decision record")
        state.decision = decision
        state.steps[-1] = replace(state.steps[-1], action=decision.action, model=decision.model, usage=dict(decision.usage))
        if state.expired():
            state.stop = "deadline"
        return {"state": state}


@component
class _Route:
    @component.output_types(again=_State, result=Result)
    def run(self, state: _State) -> dict:
        decision = state.decision
        if not state.stop and decision is not None:
            if decision.action == "retrieve":
                if len(state.queries) >= state.limits.max_retrievals:
                    state.stop = "retrieval_limit"
                elif state.model_calls >= state.limits.max_model_calls:
                    state.stop = "model_call_limit"
                else:
                    state.pending = decision.query
                    state.decision = None
                    return {"again": state}
            elif decision.action == "answer":
                if not decision.citation_ids or not set(decision.citation_ids) <= state.evidence.keys():
                    raise StrategyError("An answer must cite only evidence supplied to the decider")
                state.stop = "answered"
            else:
                state.stop = "abstained"
        citations = tuple(state.evidence[key] for key in dict.fromkeys(decision.citation_ids)) if state.stop == "answered" else ()
        answer = decision.answer if state.stop == "answered" else "Insufficient verified evidence for an answer within this experiment's limits."
        return {"result": Result(answer, citations, tuple(state.evidence.values()), tuple(state.steps), state.stop,
            len(state.queries), state.model_calls, time.monotonic() - state.started, state.strategy)}


def run(question: Question, *, retrieve: Retriever, decide: Decider,
        strategy: str = "iterative", limits: Limits | None = None) -> Result:
    """Run single-pass or bounded iterative RAG using a fresh Haystack graph.

    The retriever must already enforce the caller's scope and permissions.
    Deadlines are cooperative between calls; adapters also need network timeouts.
    A citation check validates evidence identity, not the factual truth of prose.
    """
    if strategy not in {"single-pass", "iterative"}:
        raise StrategyError("Unknown strategy")
    limits = limits or Limits()
    if strategy == "single-pass":
        limits = replace(limits, max_retrievals=1, max_model_calls=1)
    pipeline = Pipeline(max_runs_per_component=max(limits.max_retrievals, limits.max_model_calls) + 2)
    pipeline.add_component("state", BranchJoiner(type_=_State))
    pipeline.add_component("retrieve", _Retrieve(retrieve))
    pipeline.add_component("decide", _Decide(decide))
    pipeline.add_component("route", _Route())
    pipeline.connect("state.value", "retrieve.state")
    pipeline.connect("retrieve.state", "decide.state")
    pipeline.connect("decide.state", "route.state")
    pipeline.connect("route.again", "state.value")
    try:
        output = pipeline.run({"state": {"value": _State(question, limits, strategy)}})
    except PipelineRuntimeError as exc:
        if isinstance(exc.__cause__, StrategyError):
            raise exc.__cause__ from None
        raise StrategyError("A RAG adapter failed; inspect its local exception in Python") from exc
    return output["route"]["result"]
