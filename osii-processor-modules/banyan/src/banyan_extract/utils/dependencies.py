# Dependency Detection Utilities
# This module provides simple dependency detection functions
# It includes support for marker, nemotronparse, and Tesseract OCR dependencies

import importlib
from functools import lru_cache
from typing import Dict, Optional

class DependencyError(Exception):
    """Custom exception for dependency-related errors."""
    pass


@lru_cache(maxsize=32)
def has_marker_dependencies() -> bool:
    """Check if marker optional dependencies are available.
    
    Returns:
        True if all required dependencies are available, False otherwise
    """
    try:
        importlib.import_module('marker_pdf')
        importlib.import_module('surya_ocr')
        return True
    except ImportError:
        return False
    except Exception:
        return False


@lru_cache(maxsize=32)
def has_nemotronparse_dependencies() -> bool:
    """Check if nemotronparse optional dependencies are available.
    
    Returns:
        True if the required dependency is available, False otherwise
    """
    try:
        importlib.import_module('openai')
        return True
    except ImportError:
        return False
    except Exception:
        return False


def get_dependency_info() -> Dict[str, Dict[str, str]]:
    """Get detailed information about all optional dependencies.
    
    Returns:
        Dictionary containing dependency information including availability and versions
    """
    all_dependencies = {
        'marker': ['marker_pdf', 'surya_ocr'],
        'nemotronparse': ['openai']
    }
    
    dependency_info = {}
    
    for group_name, packages in all_dependencies.items():
        group_info = {}
        for package_name in packages:
            package_info = {
                'available': False,
                'version': None,
                'error': None
            }
            
            try:
                module = importlib.import_module(package_name)
                package_info['available'] = True
                
                if hasattr(module, '__version__'):
                    package_info['version'] = module.__version__
                elif hasattr(module, 'version'):
                    package_info['version'] = module.version
                
            except ImportError as e:
                package_info['error'] = f"Import failed: {e}"
            except Exception as e:
                package_info['error'] = f"Unexpected error: {e}"
            
            group_info[package_name] = package_info
        
        dependency_info[group_name] = group_info
    
    return dependency_info


def safe_check_dependency(package_name: str, fallback: bool = True) -> bool:
    """Safely check if a dependency is available.
    
    Args:
        package_name: Name of the package to check
        fallback: Whether to use fallback mechanism on error (default: True)
        
    Returns:
        True if dependency is available, False otherwise
    """
    try:
        importlib.import_module(package_name)
        return True
    except ImportError:
        return False
    except Exception:
        if fallback:
            return False
        else:
            raise DependencyError(f"Safe dependency check failed for {package_name}")


def get_installation_instructions() -> Dict[str, str]:
    """Get installation instructions for missing dependencies.
    
    Returns:
        Dictionary with installation instructions for each dependency group
    """
    standard_instructions = {
        'marker': "pip install .[marker]",
        'nemotronparse': "pip install .[nemotronparse]",
        'marker_nemotronparse': "pip install .[marker,nemotronparse]"
    }
    
    try:
        dependency_info = get_dependency_info()
        
        marker_missing = any(not p['available'] for p in dependency_info.get('marker', {}).values())
        nemotronparse_missing = any(not p['available'] for p in dependency_info.get('nemotronparse', {}).values())
        
        instructions = {}
        
        if marker_missing:
            instructions['marker'] = standard_instructions['marker']
        if nemotronparse_missing:
            instructions['nemotronparse'] = standard_instructions['nemotronparse']
        
        if marker_missing and nemotronparse_missing:
            instructions['marker_nemotronparse'] = standard_instructions['marker_nemotronparse']
        
        if 'marker' not in instructions:
            instructions['marker'] = standard_instructions['marker']
        if 'nemotronparse' not in instructions:
            instructions['nemotronparse'] = standard_instructions['nemotronparse']
        
        return instructions
        
    except Exception:
        return standard_instructions


def log_dependency_status():
    """Log the current status of all optional dependencies.
    
    This function provides a comprehensive status report of all optional dependencies.
    """
    try:
        dependency_info = get_dependency_info()
        
        print("Dependency Status:")
        for group_name, packages in dependency_info.items():
            group_status = "Available" if all(p['available'] for p in packages.values()) else "Not Available"
            print(f"  {group_name}: {group_status}")
            
            for package_name, package_info in packages.items():
                if package_info['available']:
                    version_str = f" v{package_info['version']}" if package_info['version'] else ""
                    print(f"    - {package_name}{version_str}")
                else:
                    error_msg = f" ({package_info['error']})" if package_info['error'] else ""
                    print(f"    - {package_name}: Not available{error_msg}")
        
        missing_marker = any(not p['available'] for p in dependency_info.get('marker', {}).values())
        missing_nemotronparse = any(not p['available'] for p in dependency_info.get('nemotronparse', {}).values())
        
        if missing_marker or missing_nemotronparse:
            print("\nInstallation guidance:")
            if missing_marker:
                print("  Marker PDF processor disabled: pip install .[marker]")
            if missing_nemotronparse:
                print("  Nemotron-parse processor disabled: pip install .[nemotronparse]")
            if missing_marker and missing_nemotronparse:
                print("  To install both: pip install .[marker,nemotronparse]")
       
    except Exception as e:
        print(f"Error logging dependency status: {e}")
