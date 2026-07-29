"""PDF rendering helpers."""

from __future__ import annotations

import cv2
import fitz
import numpy as np


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
    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError("Invalid or unsupported PDF document") from exc

    images: list[np.ndarray] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

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
        images.append(image)

    return images