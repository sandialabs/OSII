"""Data models for OCR processing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PSMValue = Literal["auto", "6", "7", "8", "11", "13"]


class DetectionParams(BaseModel):
    """OpenCV detection parameter set."""

    threshold_mode: Literal["adaptive", "otsu"] = "adaptive"
    blur_kernel: int = Field(3, ge=1, le=21)
    adaptive_block_size: int = Field(31, ge=3, le=101)
    adaptive_c: int = Field(15, ge=-100, le=100)

    open_kernel_w: int = Field(4, ge=1, le=20)
    open_kernel_h: int = Field(2, ge=1, le=20)

    dilate_kernel_w: int = Field(30, ge=1, le=100)
    dilate_kernel_h: int = Field(30, ge=1, le=100)
    dilate_iterations: int = Field(1, ge=1, le=10)

    min_contour_area: int = Field(50, ge=0, le=500000)
    min_width: int = Field(10, ge=0, le=10000)
    min_height: int = Field(8, ge=0, le=10000)
    bbox_padding: int = Field(4, ge=0, le=200)
    max_regions: int = Field(200, ge=1, le=5000)

    @field_validator("blur_kernel", "adaptive_block_size")
    @classmethod
    def validate_odd_kernel(cls, value: int) -> int:
        """Ensure certain kernel sizes are odd.

        Parameters
        ----------
        value : int
            Kernel size.

        Returns
        -------
        int
            Validated kernel size.
        """
        if value % 2 == 0:
            return value + 1
        return value


class RecognitionParams(BaseModel):
    """Tesseract recognition parameter set."""

    language: str = "en"
    tesseract_psm: PSMValue = "auto"
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)


class OCRParams(BaseModel):
    """Combined OCR parameter set used by production endpoints."""

    language: str = "en"

    threshold_mode: Literal["adaptive", "otsu"] = "adaptive"
    blur_kernel: int = Field(3, ge=1, le=21)
    adaptive_block_size: int = Field(31, ge=3, le=101)
    adaptive_c: int = Field(15, ge=-100, le=100)

    open_kernel_w: int = Field(4, ge=1, le=20)
    open_kernel_h: int = Field(2, ge=1, le=20)

    dilate_kernel_w: int = Field(30, ge=1, le=100)
    dilate_kernel_h: int = Field(30, ge=1, le=100)
    dilate_iterations: int = Field(1, ge=1, le=10)

    min_contour_area: int = Field(50, ge=0, le=500000)
    min_width: int = Field(10, ge=0, le=10000)
    min_height: int = Field(8, ge=0, le=10000)
    bbox_padding: int = Field(4, ge=0, le=200)
    max_regions: int = Field(200, ge=1, le=5000)

    tesseract_psm: PSMValue = "auto"

    @field_validator("blur_kernel", "adaptive_block_size")
    @classmethod
    def validate_odd_kernel(cls, value: int) -> int:
        """Ensure certain kernel sizes are odd.

        Parameters
        ----------
        value : int
            Kernel size.

        Returns
        -------
        int
            Validated kernel size.
        """
        if value % 2 == 0:
            return value + 1
        return value


class OCRItem(BaseModel):
    """OSII-Tesseract-compatible OCR result item."""

    text: str
    bbox: list[int]
    confidence: float
    polygon: list[list[int]] | None = None


class DebugArtifacts(BaseModel):
    """Debug artifact paths or metadata."""

    images: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OCRRunResult(BaseModel):
    """OCR run result for a single page/image."""

    results: list[dict[str, Any]]
    debug: DebugArtifacts | None = None


class DocumentPageResult(BaseModel):
    """OCR result for one page of a document."""

    page_number: int
    width: int
    height: int
    results: list[dict[str, Any]]
    debug: DebugArtifacts | None = None