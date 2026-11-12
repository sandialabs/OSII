"""OpenCV preprocessing and region proposal."""

from __future__ import annotations

import cv2
import numpy as np

from app.core.models import OCRParams
from app.core.utils import order_box_points, polygon_to_bbox


def preprocess_image(
    image: np.ndarray,
    params: OCRParams,
) -> dict[str, np.ndarray]:
    """Run preprocessing stages on an image.

    Parameters
    ----------
    image : np.ndarray
        Input BGR image.
    params : OCRParams
        OCR parameters.

    Returns
    -------
    dict[str, np.ndarray]
        Intermediate images.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    blur_kernel = max(1, params.blur_kernel)
    if blur_kernel % 2 == 0:
        blur_kernel += 1

    blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)

    if params.threshold_mode == "adaptive":
        block_size = max(3, params.adaptive_block_size)
        if block_size % 2 == 0:
            block_size += 1

        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            params.adaptive_c,
        )
    else:
        _, binary = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )

    open_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (params.open_kernel_w, params.open_kernel_h),
    )
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)

    dilate_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (params.dilate_kernel_w, params.dilate_kernel_h),
    )
    dilated = cv2.dilate(cleaned, dilate_kernel, iterations=params.dilate_iterations)

    return {
        "gray": gray,
        "binary": binary,
        "cleaned": cleaned,
        "dilated": dilated,
    }


def find_text_regions(
    image: np.ndarray,
    dilated: np.ndarray,
    params: OCRParams,
) -> list[dict]:
    """Find candidate text regions from a binary image.

    Parameters
    ----------
    image : np.ndarray
        Original BGR image.
    dilated : np.ndarray
        Dilated binary image.
    params : OCRParams
        OCR parameters.

    Returns
    -------
    list[dict]
        Region dictionaries containing bbox and polygon data.
    """
    contours, _ = cv2.findContours(
        dilated,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    image_height, image_width = image.shape[:2]
    regions: list[dict] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < params.min_contour_area:
            continue

        x, y, width, height = cv2.boundingRect(contour)

        if width < params.min_width or height < params.min_height:
            continue

        if width > int(image_width * 0.98) and height > int(image_height * 0.98):
            continue

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        ordered = order_box_points(box)
        polygon = [[int(point[0]), int(point[1])] for point in ordered]
        bbox = polygon_to_bbox(polygon)

        regions.append(
            {
                "bbox": bbox,
                "polygon": polygon,
                "area": float(area),
                "rect": {
                    "center": [float(rect[0][0]), float(rect[0][1])],
                    "size": [float(rect[1][0]), float(rect[1][1])],
                    "angle": float(rect[2]),
                },
            }
        )

    regions.sort(key=lambda region: (region["bbox"][1], region["bbox"][0]))
    return regions