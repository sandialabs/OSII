"""Debug image rendering helpers."""

from __future__ import annotations

import cv2
import numpy as np


def ensure_bgr(image: np.ndarray) -> np.ndarray:
    """Convert a grayscale image to BGR if needed.

    Parameters
    ----------
    image : np.ndarray
        Input image.

    Returns
    -------
    np.ndarray
        BGR image.
    """
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image.copy()


def draw_regions(image: np.ndarray, regions: list[dict], results: list[dict]) -> np.ndarray:
    """Draw region proposals and OCR boxes on an image.

    Parameters
    ----------
    image : np.ndarray
        Source image.
    regions : list[dict]
        Proposed regions.
    results : list[dict]
        OCR results.

    Returns
    -------
    np.ndarray
        Overlay image.
    """
    overlay = image.copy()

    for index, region in enumerate(regions, start=1):
        polygon = region.get("polygon")
        if polygon:
            pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(overlay, [pts], isClosed=True, color=(0, 255, 255), thickness=2)

        x1, y1, x2, y2 = region["bbox"]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), 1)
        cv2.putText(
            overlay,
            str(index),
            (x1, max(0, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 0, 0),
            1,
            cv2.LINE_AA,
        )

    for result in results:
        x1, y1, x2, y2 = result["bbox"]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 200, 0), 2)

    return overlay