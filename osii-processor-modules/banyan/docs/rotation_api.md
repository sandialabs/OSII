# Banyan Extract Rotation API Documentation

This document provides concise API documentation for the rotation detection feature in Banyan Extract.

## Rotation Detection Utilities

### Overview

The rotation detection utilities provide Tesseract OCR-based rotation detection using OSD (Orientation and Script Detection).

**Key Features**:
- Automatic rotation detection using Tesseract OSD
- Configurable confidence threshold (default: 0.7)
- Support for 0°, 90°, 180°, and 270° detection
- Graceful fallback to 0° rotation on errors
- Comprehensive error handling and logging

### Exception Classes

#### `RotationDetectionError`

**Location**: `banyan_extract.utils.rotation_detection.RotationDetectionError`

**Description**: Base exception class for all rotation detection errors.

#### `TesseractNotFoundError`

**Location**: `banyan_extract.utils.rotation_detection.TesseractNotFoundError`

**Description**: Exception raised when Tesseract OCR is not found or not properly installed.

#### `InvalidImageError`

**Location**: `banyan_extract.utils.rotation_detection.InvalidImageError`

**Description**: Exception raised when an invalid image is provided for rotation detection.

### Core Functions

#### `detect_rotation_angle(image, confidence_threshold=0.7, pytesseract_config=None)`

**Location**: `banyan_extract.utils.rotation_detection.detect_rotation_angle`

**Description**: Detect rotation angle using Tesseract OSD with comprehensive error handling and validation.

**Parameters**:
- `image` (PIL.Image): PIL Image object to analyze for rotation
- `confidence_threshold` (float): Minimum confidence required for rotation detection (0.0 to 1.0, default: 0.7)
- `pytesseract_config` (str): Optional Tesseract configuration string (default: '--psm 0')

**Returns**: Detected rotation angle in degrees (0, 90, 180, 270), or 0.0 if detection fails

**Raises**:
- `InvalidImageError`: If image is None or not a PIL Image object
- `TesseractNotFoundError`: If Tesseract dependencies are not available
- `RotationDetectionError`: If rotation detection fails unexpectedly

**Example Usage**:

```python
from PIL import Image
from banyan_extract.utils.rotation_detection import detect_rotation_angle

image = Image.open('document.jpg')
try:
    angle = detect_rotation_angle(image, confidence_threshold=0.7)
    if angle != 0:
        print(f"Detected rotation: {angle} degrees")
except Exception as e:
    print(f"Rotation detection failed: {e}")
```

#### `detect_rotation_angle_with_fallback(image, confidence_threshold=0.7, pytesseract_config=None)`

**Location**: `banyan_extract.utils.rotation_detection.detect_rotation_angle_with_fallback`

**Description**: Detect rotation angle with automatic fallback to 0 degrees on any error. This is a convenience function that wraps `detect_rotation_angle()` and handles all exceptions gracefully.

**Parameters**:
- `image` (PIL.Image): PIL Image object to analyze for rotation
- `confidence_threshold` (float): Minimum confidence required for rotation detection (0.0 to 1.0, default: 0.7)
- `pytesseract_config` (str): Optional Tesseract configuration string

**Returns**: Detected rotation angle in degrees, or 0.0 on any error

**Features**:
- Never raises exceptions - always returns a numeric value
- Automatic fallback to 0 degrees on any error
- Comprehensive error logging for debugging
- Suitable for production environments where stability is critical

**Example Usage**:

```python
from PIL import Image
from banyan_extract.utils.rotation_detection import detect_rotation_angle_with_fallback

image = Image.open('document.jpg')
# This will never raise an exception
angle = detect_rotation_angle_with_fallback(image)
print(f"Rotation angle (with fallback): {angle} degrees")
```

#### `get_rotation_correction_info(image, confidence_threshold=0.7, pytesseract_config=None)`

**Location**: `banyan_extract.utils.rotation_detection.get_rotation_correction_info`

**Description**: Get detailed rotation correction information for debugging and logging purposes.

**Parameters**:
- `image` (PIL.Image): PIL Image object to analyze for rotation
- `confidence_threshold` (float): Minimum confidence required for rotation detection (0.0 to 1.0, default: 0.7)
- `pytesseract_config` (str): Optional Tesseract configuration string

**Returns**: Dictionary containing detailed rotation information:

```python
{
    'angle': float,           # Detected rotation angle in degrees
    'confidence': float,      # Detection confidence (0.0 to 1.0)
    'needs_correction': bool, # Whether correction is needed
    'method': str,            # Rotation detection method used
    'success': bool           # Whether detection succeeded
}
```

**Example Usage**:

```python
from PIL import Image
from banyan_extract.utils.rotation_detection import get_rotation_correction_info

image = Image.open('document.jpg')
info = get_rotation_correction_info(image)
print(f"Rotation info: {info}")
```

## Tesseract OCR Integration

### Installation Requirements

For automatic rotation detection, Tesseract OCR and pytesseract are required:

```bash
# Install pytesseract package
pip install pytesseract

# Install Tesseract OCR binary
# Linux (Ubuntu/Debian):
sudo apt install tesseract-ocr

# Linux (Fedora/RHEL):
sudo dnf install tesseract

# macOS:
brew install tesseract

# Windows:
# Download from https://github.com/tesseract-ocr/tesseract
```

### Dependency Checking

The system automatically checks for Tesseract dependencies using:

```python
from banyan_extract.utils.tesseract_dependencies import has_tesseract_dependencies

if has_tesseract_dependencies():
    print("Tesseract OCR is available")
else:
    print("Tesseract OCR is not available")
```

### Configuration

Tesseract configuration options for rotation detection:

- `--psm 0`: Automatic page segmentation mode (default)
- `--psm 1`: Automatic segmentation with OSD
- `--psm 3`: Fully automatic segmentation
- Custom configurations can be passed via `pytesseract_config` parameter

## Best Practices for Rotation Detection

1. **Install Dependencies**: Ensure Tesseract OCR and pytesseract are properly installed
2. **Verify Installation**: Test Tesseract installation with `pytesseract.get_tesseract_version()`
3. **Use Appropriate Thresholds**: Start with default confidence threshold (0.7) and adjust as needed
4. **Check Document Content**: Ensure documents contain readable text for reliable OSD detection
5. **Monitor Performance**: Be aware of performance overhead with auto-detection
6. **Handle Large Images**: Be cautious with large RGBA images due to memory requirements
7. **Use Fallback Mechanism**: Use `detect_rotation_angle_with_fallback()` for production stability
8. **Enable Debug Logging**: Use debug logging for troubleshooting rotation detection issues

## Cross-References

For processor-specific API details, see:
- [Processor API documentation](processor_api.md)

For troubleshooting information, see:
- [Troubleshooting documentation](troubleshooting.md)