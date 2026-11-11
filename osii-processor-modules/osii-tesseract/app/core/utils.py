"""Shared utility helpers."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


def polygon_to_bbox(polygon: list[list[int]]) -> list[int]:
    """Convert a polygon to an axis-aligned bounding box.

    Parameters
    ----------
    polygon : list[list[int]]
        Four-point polygon.

    Returns
    -------
    list[int]
        Bounding box as [x1, y1, x2, y2].
    """
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def order_box_points(points: np.ndarray) -> np.ndarray:
    """Order box points as TL, TR, BR, BL.

    Parameters
    ----------
    points : np.ndarray
        Four 2D points.

    Returns
    -------
    np.ndarray
        Ordered points.
    """
    pts = np.array(points, dtype=np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(sums)]
    br = pts[np.argmax(sums)]
    tr = pts[np.argmin(diffs)]
    bl = pts[np.argmax(diffs)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def pad_bbox(bbox: list[int], image_shape: tuple[int, int, int], pad: int) -> list[int]:
    """Pad a bounding box while clamping to image bounds.

    Parameters
    ----------
    bbox : list[int]
        Bounding box as [x1, y1, x2, y2].
    image_shape : tuple[int, int, int]
        Image shape.
    pad : int
        Padding in pixels.

    Returns
    -------
    list[int]
        Padded bounding box.
    """
    x1, y1, x2, y2 = bbox
    height, width = image_shape[:2]
    return [
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    ]


def normalize_bbox(bbox: list[int], image_shape: tuple[int, int, int]) -> list[float]:
    """Normalize a pixel bbox to fractions of image width and height.

    Parameters
    ----------
    bbox : list[int]
        Pixel bbox as [x1, y1, x2, y2].
    image_shape : tuple[int, int, int]
        Image shape.

    Returns
    -------
    list[float]
        Normalized bbox in [0, 1].
    """
    height, width = image_shape[:2]
    x1, y1, x2, y2 = bbox
    return [
        x1 / width,
        y1 / height,
        x2 / width,
        y2 / height,
    ]


def normalize_polygon(
    polygon: list[list[int]],
    image_shape: tuple[int, int, int],
) -> list[list[float]]:
    """Normalize polygon coordinates to fractions of image width and height.

    Parameters
    ----------
    polygon : list[list[int]]
        Pixel polygon.
    image_shape : tuple[int, int, int]
        Image shape.

    Returns
    -------
    list[list[float]]
        Normalized polygon.
    """
    height, width = image_shape[:2]
    return [[x / width, y / height] for x, y in polygon]


def load_image_bytes(file_bytes: bytes, filename: str) -> np.ndarray:
    """Load an image file from bytes.

    Parameters
    ----------
    file_bytes : bytes
        Image bytes.
    filename : str
        Source filename.

    Returns
    -------
    np.ndarray
        BGR image.

    Raises
    ------
    ValueError
        If the file cannot be opened as an image.
    """
    try:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Unsupported or invalid image file: {filename}") from exc

    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def encode_png(image: np.ndarray) -> bytes:
    """Encode an image to PNG bytes.

    Parameters
    ----------
    image : np.ndarray
        Image to encode.

    Returns
    -------
    bytes
        PNG bytes.

    Raises
    ------
    ValueError
        If encoding fails.
    """
    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode image as PNG")
    return buffer.tobytes()


def polygon_dimensions(polygon: list[list[int]]) -> tuple[int, int]:
    """Compute width and height of a 4-point polygon.

    Parameters
    ----------
    polygon : list[list[int]]
        Polygon ordered TL, TR, BR, BL.

    Returns
    -------
    tuple[int, int]
        Estimated width and height.
    """
    pts = np.array(polygon, dtype=np.float32)
    tl, tr, br, bl = pts

    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)

    width = int(round(max(width_top, width_bottom)))
    height = int(round(max(height_left, height_right)))

    return max(width, 1), max(height, 1)


def extract_polygon_crop(image: np.ndarray, polygon: list[list[int]]) -> np.ndarray | None:
    """Extract a deskewed upright crop from a 4-point polygon.

    Parameters
    ----------
    image : np.ndarray
        Source BGR image.
    polygon : list[list[int]]
        Polygon ordered TL, TR, BR, BL.

    Returns
    -------
    np.ndarray | None
        Deskewed crop, or None if extraction fails.
    """
    if not polygon or len(polygon) != 4:
        return None

    src = np.array(polygon, dtype=np.float32)
    width, height = polygon_dimensions(polygon)

    if width < 2 or height < 2:
        return None

    dst = np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )

    try:
        matrix = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(image, matrix, (width, height))
    except Exception:
        return None

    if warped is None or warped.size == 0:
        return None

    return warped