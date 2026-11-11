"""ASGI applications for the two independently registered wiki enrichers."""

from osii.processor_sdk import create_openai_processor_app

from wiki_enrichers.processors import ConceptEntityWikiEnricher, ReadableWikiEnricher


readable = ReadableWikiEnricher()
concept_entity = ConceptEntityWikiEnricher()

readable_app = create_openai_processor_app(
    descriptor=readable.descriptor,
    handler=readable.enrich,
    model_capability="chat",
)
concept_entity_app = create_openai_processor_app(
    descriptor=concept_entity.descriptor,
    handler=concept_entity.enrich,
    model_capability="chat",
)
