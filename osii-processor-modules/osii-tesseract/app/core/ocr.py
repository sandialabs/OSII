"""Tesseract OCR helpers."""

from __future__ import annotations

import cv2
import pytesseract

from app.core.languages import map_language
from app.core.utils import extract_polygon_crop


def choose_psm(crop, requested_psm: str) -> int:
    """Choose a Tesseract PSM mode.

    Parameters
    ----------
    crop : np.ndarray
        OCR crop image.
    requested_psm : str
        Requested PSM value or ``auto``.

    Returns
    -------
    int
        Tesseract PSM mode.
    """
    if requested_psm != "auto":
        return int(requested_psm)

    height, width = crop.shape[:2]
    aspect_ratio = width / max(height, 1)

    if height <= 40 and aspect_ratio >= 4.0:
        return 7

    if width <= 120 and height <= 80:
        return 8

    if aspect_ratio >= 2.5 and height <= 80:
        return 7

    return 6


def ocr_region(
    image,
    bbox: list[int],
    polygon: list[list[int]] | None,
    language_code: str,
    tesseract_psm: str,
) -> tuple[str, float]:
    """Run OCR on a region using deskewed polygon crop when available.

    Parameters
    ----------
    image : np.ndarray
        Source BGR image.
    bbox : list[int]
        Region bounding box.
    polygon : list[list[int]] | None
        Region polygon ordered TL, TR, BR, BL.
    language_code : str
        ISO 639-1 language code.
    tesseract_psm : str
        Tesseract PSM value or ``auto``.

    Returns
    -------
    tuple[str, float]
        Recognized text and normalized confidence.
    """
    crop = None
    if polygon:
        crop = extract_polygon_crop(image, polygon)

    if crop is None or crop.size == 0:
        x1, y1, x2, y2 = bbox
        crop = image[y1:y2, x1:x2]

    if crop is None or crop.size == 0:
        return "", 0.0

    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    psm = choose_psm(crop, tesseract_psm)
    tesseract_language = map_language(language_code)
    config = f"--psm {psm}"

    data = pytesseract.image_to_data(
        rgb,
        lang=tesseract_language,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    texts: list[str] = []
    confidences: list[float] = []

    total = len(data["text"])
    for index in range(total):
        text = data["text"][index].strip()
        raw_confidence = data["conf"][index]

        try:
            confidence = float(raw_confidence)
        except Exception:
            confidence = -1.0

        if text:
            texts.append(text)
            if confidence >= 0:
                confidences.append(confidence / 100.0)

    merged_text = " ".join(texts).strip()
    if not merged_text:
        return "", 0.0

    mean_confidence = sum(confidences) / len(confidences) if confidences else 1.0
    mean_confidence = max(0.0, min(1.0, mean_confidence))
    return merged_text, mean_confidence