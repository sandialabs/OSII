from osii.processor_sdk import create_processor_app
from osii.processors.text import LocalStatsKeywordsEnricher

app = create_processor_app(LocalStatsKeywordsEnricher())
