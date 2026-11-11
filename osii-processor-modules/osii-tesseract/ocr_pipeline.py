import io
from typing import List, Dict, Tuple

import cv2
import pymupdf as fitz
import numpy as np
import pytesseract
from PIL import Image


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


def map_language(lang_code: str) -> str:
    return LANG_MAP.get(lang_code.lower(), "eng")


def polygon_to_bbox(polygon: List[List[int]]) -> List[int]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def order_box_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 points as TL, TR, BR, BL.
    """
    pts = np.array(pts, dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def render_pdf_to_images(pdf_bytes: bytes, dpi: int = 200) -> List[np.ndarray]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        images.append(img)

    return images


def load_images_from_upload(file_bytes: bytes, filename: str) -> List[np.ndarray]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return render_pdf_to_images(file_bytes)

    pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return [img]


def preprocess_and_find_regions(image: np.ndarray) -> List[Dict]:
    """
    OpenCV frontend:
    - grayscale
    - thresholding to remove scanning artifacts/light stray marks
    - dilation to strengthen text
    - binarization
    - find contours/blobs
    - reject tiny blobs
    - min area rectangle
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Light denoise while preserving edges
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Adaptive threshold often works better on scanned docs with uneven lighting
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )

    # Remove isolated noise
    noise_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, noise_kernel)

    # Dilate to merge characters into word/line blobs
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    dilated = cv2.dilate(cleaned, dilate_kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_img, w_img = gray.shape
    regions = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 50:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        # Filter tiny regions
        if w < 10 or h < 8:
            continue

        # Filter extreme aspect/noise heuristics
        if w > 0.98 * w_img and h > 0.98 * h_img:
            continue

        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect)
        box = order_box_points(box)
        polygon = [[int(p[0]), int(p[1])] for p in box]
        bbox = polygon_to_bbox(polygon)

        regions.append({
            "bbox": bbox,
            "polygon": polygon,
            "area": area,
        })

    # Reading order: top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
    return regions


def ocr_region(image: np.ndarray, bbox: List[int], tess_lang: str) -> Tuple[str, float]:
    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]

    if crop.size == 0:
        return "", 0.0

    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

    data = pytesseract.image_to_data(
        rgb,
        lang=tess_lang,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )

    texts = []
    confs = []

    n = len(data["text"])
    for i in range(n):
        txt = data["text"][i].strip()
        conf_raw = data["conf"][i]

        try:
            conf = float(conf_raw)
        except Exception:
            conf = -1.0

        if txt:
            texts.append(txt)
            if conf >= 0:
                confs.append(conf / 100.0)

    text = " ".join(texts).strip()
    confidence = float(sum(confs) / len(confs)) if confs else 1.0

    return text, max(0.0, min(1.0, confidence))


def process_image(image: np.ndarray, language: str) -> List[Dict]:
    tess_lang = map_language(language)
    regions = preprocess_and_find_regions(image)

    results = []
    for region in regions:
        text, conf = ocr_region(image, region["bbox"], tess_lang)
        if not text:
            continue

        results.append({
            "text": text,
            "bbox": region["bbox"],
            "confidence": conf,
            "polygon": region["polygon"],
        })

    return results


def process_document(file_bytes: bytes, filename: str, language: str) -> List[Dict]:
    """
    Spec-compliant for images.
    For PDFs, this aggregates page OCR into one flat results array only if needed.
    If you want per-page output, that should be a separate endpoint/extension.
    """
    images = load_images_from_upload(file_bytes, filename)

    if len(images) == 1:
        return process_image(images[0], language)

    # Flatten multi-page results for now, since /ocr spec expects one results array for one image.
    all_results = []
    for page_idx, image in enumerate(images):
        page_results = process_image(image, language)
        for item in page_results:
            item["page"] = page_idx + 1
            all_results.append(item)

    return all_results
