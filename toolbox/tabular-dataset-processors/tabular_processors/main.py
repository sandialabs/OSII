"""ASGI applications for the two tabular Processor API capabilities."""

from osii_processor_sdk import create_processor_app

from tabular_processors.processors import CollectionTableEnricher, CsvTableExtractor


extractor_app = create_processor_app(CsvTableExtractor())
enricher_app = create_processor_app(CollectionTableEnricher())
