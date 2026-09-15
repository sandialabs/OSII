"""ASGI applications for the two independently registered wiki enrichers."""

from osii.processor_sdk import create_processor_app

from wiki_enrichers.processors import ConceptEntityWikiEnricher, ReadableWikiEnricher


readable_app = create_processor_app(ReadableWikiEnricher())
concept_entity_app = create_processor_app(ConceptEntityWikiEnricher())
