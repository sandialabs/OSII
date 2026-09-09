from osii.enrichment.llm_wiki import LlmWikiEnricher
from osii.enrichment.llm_wiki_stub import LlmWikiStubEnricher
from osii.enrichment.linguistic_examples import (
    EntityCandidateEnricher,
    NounAdjectiveNgramEnricher,
)
from osii.enrichment.stats_keywords import StatsKeywordsEnricher
from osii.processors.remote import RemoteEnricher, discover_remote_processors


def get_enrichers():
    local = [
        StatsKeywordsEnricher(),
        LlmWikiEnricher(),
        LlmWikiStubEnricher(),
        NounAdjectiveNgramEnricher(),
        EntityCandidateEnricher(),
    ]
    remote = [
        RemoteEnricher(item)
        for item in discover_remote_processors()
        if item.get("kind") == "enricher"
    ]
    return [*local, *remote]


def list_enricher_descriptions() -> list[dict]:
    return [item.describe() for item in get_enrichers()]


def resolve_enricher(name: str):
    for item in get_enrichers():
        if item.name == name:
            return item
    raise RuntimeError(f"Enricher '{name}' is not supported.")
