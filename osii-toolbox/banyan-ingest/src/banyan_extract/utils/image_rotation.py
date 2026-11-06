"""
Image rotation utility functions for banyan-extract.

This module provides functions for rotating PIL Image objects while maintaining
image quality and handling edge cases appropriately.
"""

from PIL import Image
from typing import Union
import math


def rotate_image(image: Image.Image, angle: Union[int, float], resample: int = Image.BICUBIC) -> Image.Image:
    """
    Rotate a PIL Image object by the specified angle.
    
    This function creates a new rotated image while maintaining image quality.
    It supports common rotation angles (0, 90, 180, 270) and handles edge cases
    such as invalid inputs and non-integer angles.
    
    Args:
        image: PIL Image object to rotate
        angle: Rotation angle in degrees (clockwise). 
               Supported values: 0, 90, 180, 270, and any other angle.
        resample: Resampling filter to use for rotation. Defaults to Image.BICUBIC.
                  Options: Image.NEAREST, Image.BILINEAR, Image.BICUBIC, Image.LANCZOS
        
    Returns:
        New PIL Image object with the rotation applied
         
    Raises:
        ValueError: If image is None or angle is invalid
        TypeError: If image is not a PIL Image object or angle is not numeric
         
    Note:
        - For angles that are not multiples of 90 degrees, the image will be
          rotated and the bounding box will be expanded to fit the rotated content.
        - The original image is not modified; a new image is returned.
        - Image quality is maintained by using appropriate resampling filters.
        - Memory considerations: Large images rotated at arbitrary angles may
          consume significant memory due to the expanded bounding box. For best
          performance with large images, use 90-degree multiples when possible.
    """
    # Validate inputs
    if image is None:
        raise ValueError("Image cannot be None")
    
    if not isinstance(image, Image.Image):
        raise TypeError("Image must be a PIL Image object")
    
    if isinstance(angle, bool):
        raise TypeError("Angle must be a numeric value")

    if not isinstance(angle, (int, float)):
        raise TypeError("Angle must be a numeric value (int or float)")
    
    # Normalize angle using the dedicated function
    angle = normalize_rotation_angle(angle)
    
    # Handle special cases for better performance and quality
    if angle == 0:
        # No rotation needed, return a copy to maintain immutability
        return image.copy()
    elif angle == 90:
        # Use transpose for 90-degree rotation (faster and maintains quality)
        return image.transpose(Image.ROTATE_90)
    elif angle == 180:
        # Use transpose for 180-degree rotation
        return image.transpose(Image.ROTATE_180)
    elif angle == 270:
        # Use transpose for 270-degree rotation
        return image.transpose(Image.ROTATE_270)
    else:
        # For other angles, use the general rotate method
        # Use expand=True to ensure the entire rotated image is visible
        # Use configurable resampling filter for quality control
        return image.rotate(angle, expand=True, resample=resample)


def is_valid_rotation_angle(angle: Union[int, float]) -> bool:
    """
    Check if a rotation angle is valid.

    Args:
        angle: Rotation angle in degrees to validate
        
    Returns:
        True if the angle is valid (numeric and finite), False otherwise
    """
    # First check if it's a boolean (since bool is a subclass of int)
    if isinstance(angle, bool):
        return False
    
    # Check if it's actually a numeric type (int or float), not just convertible to float
    if not isinstance(angle, (int, float)):
        return False
    
    # Use math.isfinite for cleaner numeric validation
    try:
        angle_float = float(angle)
        return math.isfinite(angle_float)
    except (TypeError, ValueError, OverflowError):
        return False


def normalize_rotation_angle(angle: Union[int, float]) -> float:
    """
    Normalize a rotation angle to the range [0, 360).
    
    This function uses math.fmod for robust floating-point modulo operations
    and handles negative angles explicitly for consistency.
    
    Args:
        angle: Rotation angle in degrees
        
    Returns:
        Normalized angle in the range [0, 360)
        
    Raises:
        ValueError: If angle is not a valid numeric value
    
    Examples:
        >>> normalize_rotation_angle(450)
        90.0
        >>> normalize_rotation_angle(-90)
        270.0
        >>> normalize_rotation_angle(360)
        0.0
    """
    if not is_valid_rotation_angle(angle):
        raise ValueError(f"Invalid rotation angle: {angle}")
    
    # Use math.fmod for robust floating-point modulo operations
    normalized = math.fmod(float(angle), 360.0)
    
    # Handle negative results by adding 360 to bring into [0, 360) range
    if normalized < 0:
        normalized += 360.0
    
    return normalized
