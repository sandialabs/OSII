# Tesseract Dependency Detection Utilities
# This module provides Tesseract-specific dependency detection functions

import importlib
from typing import Optional

def _check_tesseract_binary_version() -> Optional[str]:
    """Check Tesseract OCR binary version using pytesseract.
    
    Returns:
        Tesseract version string if available, None otherwise
    """
    try:
        # Import pytesseract and get version
        import pytesseract
        pytesseract_version = pytesseract.get_tesseract_version()
        
        if pytesseract_version:
            return pytesseract_version
        else:
            return None
            
    except ImportError:
        return None
    except Exception:
        return None

def has_tesseract_dependencies() -> bool:
    """Check if Tesseract OCR dependencies are available.
    
    This function checks for both the pytesseract Python package and the Tesseract OCR binary.
    
    Returns:
        True if all required dependencies are available, False otherwise
    """
    try:
        # Check pytesseract Python package
        importlib.import_module('pytesseract')
        
        # Check Tesseract OCR binary
        tesseract_binary_version = _check_tesseract_binary_version()
        if tesseract_binary_version:
            return True
        else:
            return False
            
    except ImportError:
        return False
    except Exception:
        return False