from osii.extraction.osii_tesseract_extractor import OsiiTesseractExtractor
from osii.extraction.banyan_extractor import PdfDefaultExtractor
from osii.extraction.tika_extractor import TikaCatchallExtractor
from osii.extraction.native_text_extractor import NativeTextExtractor


def get_extractors():
    return [
        NativeTextExtractor(),
        OsiiTesseractExtractor(),
        PdfDefaultExtractor(),
        TikaCatchallExtractor(),
    ]


def list_extractor_descriptions() -> list[dict]:
    return [extractor.describe() for extractor in get_extractors()]
