# Rotation Detection Module
# This module provides Tesseract OCR-based rotation detection using OSD (Orientation and Script Detection)

import logging
import sys
from typing import Optional, Tuple, Union
from PIL import Image

# Import dependency checking functions
from .tesseract_dependencies import has_tesseract_dependencies
from .dependencies import DependencyError

# Use centralized logging
from .logging_config import get_logger

logger = get_logger(__name__)


class RotationDetectionError(Exception):
    """Custom exception for rotation detection errors."""
    pass


class TesseractNotFoundError(RotationDetectionError):
    """Custom exception for Tesseract OCR not found."""
    pass


class InvalidImageError(RotationDetectionError):
    """Custom exception for invalid image inputs."""
    pass


def _validate_image(image: Image.Image) -> None:
    """Validate that the input is a valid PIL Image object.
    
    Args:
        image: PIL Image object to validate
        
    Raises:
        InvalidImageError: If image is None or not a PIL Image object
    """
    if image is None:
        raise InvalidImageError("Image cannot be None")
    
    if not isinstance(image, Image.Image):
        raise InvalidImageError("Image must be a PIL Image object")


def _preprocess_image_for_osd(image: Image.Image) -> Image.Image:
    """Preprocess image for optimal OSD (Orientation and Script Detection) performance.
    
    Args:
        image: PIL Image object to preprocess
        
    Returns:
        Preprocessed PIL Image object suitable for OSD
        
    Note:
        - Large RGBA images will generate a warning due to memory considerations
        - Images are converted to RGB format for optimal OSD performance
    """
    # Convert to RGB if not already (OSD works best with RGB)
    if image.mode != 'RGB':
        if image.mode == 'RGBA':
            # Check for large RGBA images and warn about memory usage
            width, height = image.size
            pixel_count = width * height
            if pixel_count > 1000000:  # 1 million pixels
                logger.warning(f"Large RGBA image detected ({width}x{height} = {pixel_count:,} pixels). "
                             f"Conversion to RGB may consume significant memory.")
            
            # For RGBA images, create white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
            image = background
        else:
            # For other modes (grayscale, etc.), convert to RGB
            image = image.convert('RGB')
    
    return image


def _parse_osd_output(osd_output: dict) -> Tuple[float, float]:
    """Parse Tesseract OSD output to extract rotation angle and confidence.
    
    Args:
        osd_output: Dictionary containing Tesseract OSD output
        
    Returns:
        Tuple of (rotation_angle, confidence) where:
        - rotation_angle: Detected rotation angle in degrees (0, 90, 180, 270)
        - confidence: Detection confidence (0.0 to 1.0)
        
    Raises:
        RotationDetectionError: If OSD output is invalid or missing required fields
    """
    try:
        # Extract orientation angle from OSD output
        # Tesseract OSD returns orientation in degrees (0, 90, 180, 270)
        if 'orientation' not in osd_output:
            raise RotationDetectionError("OSD output missing 'orientation' field")
        
        orientation_angle = float(osd_output['orientation'])
        
        # Extract confidence if available, default to 0.0 if not present
        confidence = 0.0
        if 'orientation_conf' in osd_output:
            confidence = float(osd_output['orientation_conf'])
        
        # Normalize confidence to 0.0-1.0 range
        original_confidence = confidence
        confidence = max(0.0, min(1.0, confidence))
        if confidence != original_confidence:
            logger.debug(f"Normalized confidence from {original_confidence} to {confidence}")
        
        return orientation_angle, confidence
        
    except (KeyError, ValueError, TypeError) as e:
        raise RotationDetectionError(f"Failed to parse OSD output: {e}") from e


def detect_rotation_angle(
    image: Image.Image,
    confidence_threshold: float = 0.7,
    pytesseract_config: Optional[str] = None
) -> float:
    """Detect the rotation angle of an image using Tesseract OSD.
    
    This function uses Tesseract OCR's Orientation and Script Detection (OSD) 
    to determine if an image is rotated and needs correction. The function 
    automatically handles dependency checking and provides appropriate fallbacks.
    
    Args:
        image: PIL Image object to analyze for rotation
        confidence_threshold: Minimum confidence required for rotation detection (0.0 to 1.0)
                              Default: 0.7 (70% confidence)
        pytesseract_config: Optional Tesseract configuration string
                           Example: '--psm 0' for automatic page segmentation
        
    Returns:
        Detected rotation angle in degrees (0, 90, 180, 270), or 0.0 if:
        - Detection confidence is below threshold
        - Tesseract dependencies are not available
        - Rotation detection fails for any reason
        
    Raises:
        InvalidImageError: If image is None or not a PIL Image object
        TesseractNotFoundError: If Tesseract dependencies are not available or pytesseract import fails
        RotationDetectionError: If rotation detection fails unexpectedly, including Tesseract OCR errors
        
    Note:
        - This function uses Tesseract OCR's OSD (Orientation and Script Detection)
        - The function returns 0.0 as fallback for any failure condition
        - For best results, use images with clear text content
        - OSD works best with document images containing readable text
        - The function automatically converts images to RGB format for OSD
        
    Examples:
        >>> from PIL import Image
        >>> image = Image.open('document.jpg')
        >>> angle = detect_rotation_angle(image)
        >>> if angle != 0:
        ...     rotated_image = rotate_image(image, angle)
    """
    # Validate input image
    _validate_image(image)
    
    # Check if Tesseract dependencies are available
    if not has_tesseract_dependencies():
        logger.warning("Tesseract OCR dependencies not available. Auto-rotation detection skipped. "
                      "To enable rotation detection, install Tesseract OCR and pytesseract package: "
                      "pip install pytesseract and install Tesseract OCR binary from https://github.com/tesseract-ocr/tesseract")
        raise TesseractNotFoundError("Tesseract OCR dependencies are not available. "
                                   "Install Tesseract OCR and pytesseract package to enable rotation detection.")
    
    try:
        # Import pytesseract (should be available since we checked dependencies)
        import pytesseract
        
        # Preprocess image for OSD
        processed_image = _preprocess_image_for_osd(image)
        
        # Set default config if not provided
        if pytesseract_config is None:
            pytesseract_config = '--psm 0'  # Automatic page segmentation mode
        
        # Validate pytesseract_config parameter
        if not isinstance(pytesseract_config, str):
            logger.error(f"Invalid pytesseract_config type: {type(pytesseract_config)}")
            raise RotationDetectionError(f"pytesseract_config must be a string, got {type(pytesseract_config)}")
        
        # Add timing for Tesseract operations for performance monitoring
        import time
        start_time = time.time()
        
        # Use Tesseract OSD to detect orientation
        logger.debug(f"Running Tesseract OSD with config: {pytesseract_config}")
        osd_output = pytesseract.image_to_osd(processed_image, config=pytesseract_config, output_type=pytesseract.Output.DICT)
        
        # Log performance timing
        elapsed_time = time.time() - start_time
        logger.debug(f"Tesseract OSD completed in {elapsed_time:.3f} seconds")
        
        # Parse OSD output
        rotation_angle, confidence = _parse_osd_output(osd_output)
        
        # Check if confidence meets threshold
        if confidence >= confidence_threshold:
            # Normalize angle to standard range
            normalized_angle = rotation_angle % 360
            logger.info(f"Rotation detected: {normalized_angle} degrees (confidence: {confidence:.2f})")
            return float(normalized_angle)
        else:
            logger.info(f"Rotation detection confidence {confidence:.2f} below threshold {confidence_threshold}. Using 0 degrees.")
            return 0.0
            
    except ImportError as e:
        logger.error(f"Failed to import pytesseract: {e}")
        logger.warning("pytesseract package not found. Install it with: pip install pytesseract")
        raise TesseractNotFoundError(f"pytesseract import failed: {e}. "
                                   "Install pytesseract package with 'pip install pytesseract' to enable rotation detection.") from e
        
    except Exception as e:
        # Handle specific Tesseract exceptions using isinstance() checks
        # First try to get exception classes from pytesseract if available
        try:
            import pytesseract
            TesseractNotFoundErrorClass = getattr(pytesseract, 'TesseractNotFoundError', None)
            TesseractErrorClass = getattr(pytesseract, 'TesseractError', None)
        except ImportError:
            TesseractNotFoundErrorClass = None
            TesseractErrorClass = None
            
        # Try isinstance() checks first (preferred method)
        exception_handled = False
        try:
            if TesseractNotFoundErrorClass is not None and isinstance(e, TesseractNotFoundErrorClass):
                logger.error(f"Tesseract OCR binary not found: {e}")
                logger.warning("Tesseract OCR binary not found. Install Tesseract OCR from https://github.com/tesseract-ocr/tesseract")
                raise TesseractNotFoundError(f"Tesseract OCR binary not found: {e}. "
                                           "Install Tesseract OCR binary to enable rotation detection.") from e
                exception_handled = True
            elif TesseractErrorClass is not None and isinstance(e, TesseractErrorClass):
                logger.error(f"Tesseract OCR error during rotation detection: {e}")
                raise RotationDetectionError(f"Tesseract OCR error: {e}") from e
                exception_handled = True
        except TypeError:
            # isinstance() failed, fall back to string-based exception name checking
            exception_name = type(e).__name__
            if exception_name == 'TesseractNotFoundError':
                logger.error(f"Tesseract OCR binary not found: {e}")
                logger.warning("Tesseract OCR binary not found. Install Tesseract OCR from https://github.com/tesseract-ocr/tesseract")
                raise TesseractNotFoundError(f"Tesseract OCR binary not found: {e}. "
                                           "Install Tesseract OCR binary to enable rotation detection.") from e
                exception_handled = True
            elif exception_name == 'TesseractError':
                logger.error(f"Tesseract OCR error during rotation detection: {e}")
                raise RotationDetectionError(f"Tesseract OCR error: {e}") from e
                exception_handled = True
        
        if not exception_handled:
            if isinstance(e, RotationDetectionError):
                # Re-raise RotationDetectionError as-is
                raise
            else:
                # Handle other exceptions
                logger.error(f"Unexpected error during rotation detection: {e}")
                raise RotationDetectionError(f"Rotation detection failed: {e}") from e


def detect_rotation_angle_with_fallback(
    image: Image.Image,
    confidence_threshold: float = 0.7,
    pytesseract_config: Optional[str] = None
) -> float:
    """Detect rotation angle with automatic fallback to 0 degrees on any error.
    
    This is a convenience function that wraps detect_rotation_angle() and 
    automatically handles all exceptions by returning 0.0 as fallback.
    
    Args:
        image: PIL Image object to analyze for rotation
        confidence_threshold: Minimum confidence required for rotation detection (0.0 to 1.0)
        pytesseract_config: Optional Tesseract configuration string
        
    Returns:
        Detected rotation angle in degrees, or 0.0 on any error
        
    Note:
        This function never raises exceptions - it always returns a numeric value.
    """
    try:
        return detect_rotation_angle(image, confidence_threshold, pytesseract_config)
    except Exception as e:
        logger.warning(f"Rotation detection failed, using fallback: {e}")
        return 0.0



