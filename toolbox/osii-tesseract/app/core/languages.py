"""Language mapping utilities."""

from __future__ import annotations

LANG_MAP = {
    "en": "eng",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
    "ja": "jpn",
    "ko": "kor",
    "zh": "chi_sim",
    "ar": "ara",
}


def map_language(language_code: str) -> str:
    """Map an ISO 639-1 language code to a Tesseract language code.

    Parameters
    ----------
    language_code : str
        ISO 639-1 language code.

    Returns
    -------
    str
        Tesseract language code.
    """
    if not language_code:
        return "eng"
    return LANG_MAP.get(language_code.lower(), "eng")