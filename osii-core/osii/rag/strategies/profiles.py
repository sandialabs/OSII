"""Versioned query-time profiles. Selecting one never rebuilds a corpus/index."""
from dataclasses import dataclass

from .contracts import StrategyError


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    retrieval: str
    strategy: str = "single-pass"
    rerank: bool = False
    candidates: int = 8
    evidence: int = 8
    rounds: int = 1

    def __post_init__(self):
        if not self.id or len(self.id) > 100 or not self.name:
            raise StrategyError("A profile requires a bounded ID and name")
        if self.retrieval not in {"lexical", "hybrid", "semantic"} or self.strategy not in {"single-pass", "iterative"}:
            raise StrategyError("Unsupported profile retrieval or strategy")
        if not 1 <= self.evidence <= self.candidates <= 50 or not 1 <= self.rounds <= 8:
            raise StrategyError("Profile budgets exceed the supported limits")
        if self.strategy == "single-pass" and self.rounds != 1:
            raise StrategyError("Single-pass profiles use exactly one round")


PROFILES = (
    Profile("lexical-v1", "Keyword baseline", "One keyword retrieval followed by a grounded answer.", "lexical"),
    Profile("hybrid-v1", "Hybrid baseline", "Keyword and vector retrieval; actual retrieval fallback is reported.", "hybrid"),
    Profile("hybrid-reranked-v1", "Hybrid + reranker", "Retrieve up to 40 passages; rerank and retain up to 8.", "hybrid", rerank=True, candidates=40),
    Profile("iterative-v1", "Iterative hybrid", "Up to three focused searches and chat decisions within the same scope.", "hybrid", strategy="iterative", rounds=3),
)


def get_profile(identifier: str) -> Profile:
    for profile in PROFILES:
        if profile.id == identifier:
            return profile
    raise StrategyError("Unknown RAG profile")
