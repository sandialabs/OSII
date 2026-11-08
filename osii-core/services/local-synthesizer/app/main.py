from osii.processor_sdk import create_processor_app
from osii.processors.text import LocalExtractivePreviewSynthesizer

app = create_processor_app(LocalExtractivePreviewSynthesizer())
