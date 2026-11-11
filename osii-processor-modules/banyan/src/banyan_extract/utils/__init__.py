# Utilities module
# This module provides utility functions for the banyan-extract package

from .dependencies import (
    has_marker_dependencies,
    has_nemotronparse_dependencies,
    get_dependency_info,
    log_dependency_status,
    DependencyError
)

from .tesseract_dependencies import (
    has_tesseract_dependencies,
    _check_tesseract_binary_version
)

from .image_rotation import (
    rotate_image,
    is_valid_rotation_angle,
    normalize_rotation_angle
)

from .rotation_detection import (
    detect_rotation_angle,
    detect_rotation_angle_with_fallback,
    RotationDetectionError,
    TesseractNotFoundError,
    InvalidImageError
)

from .file_gather import gather_files

from .setup_nemoparse_config import get_nemoparse_config
