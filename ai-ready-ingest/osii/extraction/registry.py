from osii.extraction.osii_tesseract_extractor import OsiiTesseractExtractor
from osii.extraction.banyan_extractor import PdfDefaultExtractor
from osii.extraction.textract_extractor import TextractExtractor
from osii.extraction.tika_extractor import TikaCatchallExtractor


def get_extractors():
    return [
        OsiiTesseractExtractor(),
        PdfDefaultExtractor(),
        TextractExtractor(),
        TikaCatchallExtractor(),
    ]


def list_extractor_descriptions() -> list[dict]:
    return [extractor.describe() for extractor in get_extractors()]