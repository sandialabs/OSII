"""PDF rendering helpers."""

from __future__ import annotations

from collections.abc import Iterator

import cv2
import fitz
import numpy as np


def pdf_page_count(file_bytes: bytes) -> int:
    """Return a PDF's page count without rendering its pages."""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            return int(document.page_count)
    except Exception as exc:
        raise ValueError("Invalid or unsupported PDF document") from exc


def iter_pdf_pages(file_bytes: bytes, dpi: int = 200) -> Iterator[np.ndarray]:
    """Yield BGR page images one at a time to bound memory usage."""
    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError("Invalid or unsupported PDF document") from exc

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )
            if pixmap.n == 3:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            elif pixmap.n == 4:
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            yield image
    finally:
        document.close()


def render_pdf_pages(file_bytes: bytes, dpi: int = 200) -> list[np.ndarray]:
    """Render a PDF into page images.

    Parameters
    ----------
    file_bytes : bytes
        PDF bytes.
    dpi : int, optional
        Render DPI, by default 200.

    Returns
    -------
    list[np.ndarray]
        List of BGR page images.

    Raises
    ------
    ValueError
        If the PDF cannot be opened or rendered.
    """
    return list(iter_pdf_pages(file_bytes, dpi=dpi))
