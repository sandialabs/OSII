"""Shared OCR pipeline."""

from __future__ import annotations

from app.config import settings
from app.core.debug import draw_regions
from app.core.models import (
    DebugArtifacts,
    DetectionParams,
    DocumentPageResult,
    OCRParams,
    OCRRunResult,
    RecognitionParams,
)
from app.core.ocr import ocr_region
from app.core.pdf import render_pdf_pages
from app.core.preprocess import find_text_regions, preprocess_image
from app.core.utils import load_image_bytes, normalize_bbox, normalize_polygon, pad_bbox

def detect_page_regions(
    image,
    params: DetectionParams,
    include_debug: bool = False,
) -> tuple[list[dict], DebugArtifacts | None, dict[str, object]]:
    """Detect candidate text regions for a page image.

    Parameters
    ----------
    image : np.ndarray
        BGR image.
    params : DetectionParams
        Detection parameters.
    include_debug : bool, optional
        Whether to produce debug images, by default False.

    Returns
    -------
    tuple[list[dict], DebugArtifacts | None, dict[str, object]]
        Detected regions, debug metadata, and raw debug images.
    """
    print("[pipeline] detect_page_regions start", flush=True)

    stages = preprocess_image(image, params)
    regions = find_text_regions(image, stages["dilated"], params)

    print(f"[pipeline] regions found before cap: {len(regions)}", flush=True)
    if params.max_regions and len(regions) > params.max_regions:
        print(
            f"[pipeline] capping regions from {len(regions)} to {params.max_regions}",
            flush=True,
        )
        regions = regions[: params.max_regions]
    print(f"[pipeline] regions used: {len(regions)}", flush=True)

    debug = None
    debug_images: dict[str, object] = {}

    if include_debug:
        overlay = draw_regions(image, regions, [])
        debug_images = {
            "original": image,
            "gray": stages["gray"],
            "binary": stages["binary"],
            "cleaned": stages["cleaned"],
            "dilated": stages["dilated"],
            "overlay": overlay,
        }
        debug = DebugArtifacts(
            images={},
            metadata={
                "num_regions": len(regions),
                "page_width": int(image.shape[1]),
                "page_height": int(image.shape[0]),
            },
        )

    print("[pipeline] detect_page_regions done", flush=True)
    return regions, debug, debug_images


def ocr_page_regions(
    image,
    regions: list[dict],
    detection_params: DetectionParams,
    recognition_params: RecognitionParams,
    include_debug: bool = False,
) -> tuple[OCRRunResult, dict[str, object]]:
    """Run OCR on a precomputed set of regions.

    Parameters
    ----------
    image : np.ndarray
        BGR page image.
    regions : list[dict]
        Detected regions.
    detection_params : DetectionParams
        Detection parameters.
    recognition_params : RecognitionParams
        Recognition parameters.
    include_debug : bool, optional
        Whether to include debug images, by default False.

    Returns
    -------
    tuple[OCRRunResult, dict[str, object]]
        OCR run result and raw debug images.
    """
    print(f"[pipeline] ocr_page_regions start with {len(regions)} regions", flush=True)

    results: list[dict] = []
    for index, region in enumerate(regions, start=1):
        if index == 1 or index % 10 == 0:
            print(f"[pipeline] OCR region {index}/{len(regions)}", flush=True)

        padded_bbox = pad_bbox(region["bbox"], image.shape, detection_params.bbox_padding)
        text, confidence = ocr_region(
            image=image,
            bbox=padded_bbox,
            polygon=region.get("polygon"),
            language_code=recognition_params.language,
            tesseract_psm=recognition_params.tesseract_psm,
        )
        if not text:
            continue
        if confidence < recognition_params.confidence_threshold:
            continue

        results.append(
            {
                "text": text,
                "bbox": normalize_bbox(region["bbox"], image.shape),
                "confidence": confidence,
                "polygon": normalize_polygon(region["polygon"], image.shape)
                if region.get("polygon")
                else None,
            }
        )

    debug = None
    debug_images: dict[str, object] = {}

    if include_debug:
        overlay = draw_regions(image, regions, results)
        debug_images = {
            "overlay": overlay,
        }
        debug = DebugArtifacts(
            images={},
            metadata={
                "num_regions": len(regions),
                "num_ocr_results": len(results),
                "page_width": int(image.shape[1]),
                "page_height": int(image.shape[0]),
            },
        )

    print(f"[pipeline] ocr_page_regions done, OCR results: {len(results)}", flush=True)
    return OCRRunResult(results=results, debug=debug), debug_images


def process_page_image(
    image,
    params: OCRParams,
    include_debug: bool = False,
) -> tuple[OCRRunResult, dict[str, object]]:
    """Process a single page image end-to-end.

    Parameters
    ----------
    image : np.ndarray
        BGR image.
    params : OCRParams
        OCR parameters.
    include_debug : bool, optional
        Whether to include debug images, by default False.

    Returns
    -------
    tuple[OCRRunResult, dict[str, object]]
        OCR run result and raw debug images.
    """
    detection_params = DetectionParams(
        threshold_mode=params.threshold_mode,
        blur_kernel=params.blur_kernel,
        adaptive_block_size=params.adaptive_block_size,
        adaptive_c=params.adaptive_c,
        open_kernel_w=params.open_kernel_w,
        open_kernel_h=params.open_kernel_h,
        dilate_kernel_w=params.dilate_kernel_w,
        dilate_kernel_h=params.dilate_kernel_h,
        dilate_iterations=params.dilate_iterations,
        min_contour_area=params.min_contour_area,
        min_width=params.min_width,
        min_height=params.min_height,
        bbox_padding=params.bbox_padding,
        max_regions=params.max_regions,
    )
    recognition_params = RecognitionParams(
        language=params.language,
        tesseract_psm=params.tesseract_psm,
        confidence_threshold=0.0,
    )

    regions, _, detect_debug_images = detect_page_regions(
        image=image,
        params=detection_params,
        include_debug=include_debug,
    )
    run, ocr_debug_images = ocr_page_regions(
        image=image,
        regions=regions,
        detection_params=detection_params,
        recognition_params=recognition_params,
        include_debug=include_debug,
    )

    debug_images = {**detect_debug_images, **ocr_debug_images}
    return run, debug_images


def process_image_bytes(
    file_bytes: bytes,
    filename: str,
    params: OCRParams,
    include_debug: bool = False,
) -> OCRRunResult:
    """Process a single uploaded image.

    Parameters
    ----------
    file_bytes : bytes
        Uploaded image bytes.
    filename : str
        Source filename.
    params : OCRParams
        OCR parameters.
    include_debug : bool, optional
        Whether to include debug images, by default False.

    Returns
    -------
    OCRRunResult
        OCR result for the image.
    """
    print(f"[pipeline] process_image_bytes start: {filename}", flush=True)

    if filename.lower().endswith(".pdf"):
        raise ValueError("The /ocr endpoint expects an image file, not a PDF")

    image = load_image_bytes(file_bytes, filename)
    run, _ = process_page_image(image, params, include_debug=include_debug)

    print("[pipeline] process_image_bytes done", flush=True)
    return run


def process_document_bytes(
    file_bytes: bytes,
    filename: str,
    params: OCRParams,
    include_debug: bool = False,
) -> list[DocumentPageResult]:
    """Process an uploaded image or PDF and return per-page results.

    Parameters
    ----------
    file_bytes : bytes
        Uploaded file bytes.
    filename : str
        Source filename.
    params : OCRParams
        OCR parameters.
    include_debug : bool, optional
        Whether to include debug metadata, by default False.

    Returns
    -------
    list[DocumentPageResult]
        Per-page OCR results.
    """
    print(f"[pipeline] process_document_bytes start: {filename}", flush=True)

    if filename.lower().endswith(".pdf"):
        images = render_pdf_pages(file_bytes, dpi=settings.default_pdf_dpi)
    else:
        images = [load_image_bytes(file_bytes, filename)]

    pages: list[DocumentPageResult] = []
    for index, image in enumerate(images, start=1):
        print(f"[pipeline] processing page {index}/{len(images)}", flush=True)
        run, _ = process_page_image(image, params, include_debug=include_debug)
        pages.append(
            DocumentPageResult(
                page_number=index,
                width=int(image.shape[1]),
                height=int(image.shape[0]),
                results=run.results,
                debug=run.debug,
            )
        )

    print("[pipeline] process_document_bytes done", flush=True)
    return pages