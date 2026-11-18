from osii.extraction.banyan_extractor import PdfDefaultExtractor
from osii.extraction.tika_extractor import TikaCatchallExtractor
from osii.extraction.native_text_extractor import NativeTextExtractor
import os


def get_extractors():
    if os.getenv("OSII_STANDALONE") == "1":
        return [NativeTextExtractor()]
    return [
        NativeTextExtractor(),
        PdfDefaultExtractor(),
        TikaCatchallExtractor(),
    ]


def list_extractor_descriptions() -> list[dict]:
    return [extractor.describe() for extractor in get_extractors()]
