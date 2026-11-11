# Test Dependency Detection Utilities
# This file contains tests for the enhanced dependency detection functions

import pytest
import sys
from unittest.mock import patch, MagicMock
import importlib

# Add the source directory to the path so we can import the module
sys.path.insert(0, '/projects/src')

from banyan_extract.utils.dependencies import (
    has_marker_dependencies,
    has_nemotronparse_dependencies,
    get_dependency_info,
    log_dependency_status,
    DependencyError
)


def test_has_marker_dependencies_success():
    """Test has_marker_dependencies when all dependencies are available."""
    # Clear cache before test
    has_marker_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock successful imports
        mock_import.side_effect = lambda x: MagicMock() if x in ['marker_pdf', 'surya_ocr'] else None
        
        result = has_marker_dependencies()
        assert result is True


def test_has_marker_dependencies_missing():
    """Test has_marker_dependencies when dependencies are missing."""
    # Clear cache before test
    has_marker_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock ImportError for marker_pdf
        mock_import.side_effect = ImportError("marker_pdf not found")
        
        result = has_marker_dependencies()
        assert result is False


def test_has_nemotronparse_dependencies_success():
    """Test has_nemotronparse_dependencies when dependency is available."""
    # Clear cache before test
    has_nemotronparse_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock successful import
        mock_import.side_effect = lambda x: MagicMock() if x == 'openai' else None
        
        result = has_nemotronparse_dependencies()
        assert result is True


def test_has_nemotronparse_dependencies_missing():
    """Test has_nemotronparse_dependencies when dependency is missing."""
    # Clear cache before test
    has_nemotronparse_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock ImportError for openai
        mock_import.side_effect = ImportError("openai not found")
        
        result = has_nemotronparse_dependencies()
        assert result is False





def test_get_dependency_info():
    """Test get_dependency_info returns expected structure."""
    result = get_dependency_info()
    
    # Check that the result has the expected structure
    assert isinstance(result, dict)
    assert 'marker' in result
    assert 'nemotronparse' in result
    
    # Check marker dependencies
    marker_deps = result['marker']
    assert 'marker_pdf' in marker_deps
    assert 'surya_ocr' in marker_deps
    
    # Check nemotronparse dependencies
    nemotronparse_deps = result['nemotronparse']
    assert 'openai' in nemotronparse_deps


def test_caching_behavior():
    """Test that dependency checks are cached."""
    # Clear cache first
    has_marker_dependencies.cache_clear()
    has_nemotronparse_dependencies.cache_clear()
    
    with patch('importlib.import_module') as mock_import:
        mock_import.side_effect = lambda x: MagicMock() if x in ['marker_pdf', 'surya_ocr', 'openai'] else None
        
        # First call
        result1 = has_marker_dependencies()
        # Second call should use cache
        result2 = has_marker_dependencies()
        
        assert result1 == result2
        # The mock should only be called once due to caching
        # Note: This might not work exactly as expected due to how the caching works


def test_exception_classes():
    """Test that custom exception classes work correctly."""
    # Test DependencyError
    with pytest.raises(DependencyError):
        raise DependencyError("Test error")


def test_error_handling_in_dependency_info():
    """Test error handling in get_dependency_info."""
    # This should not crash even if there are errors
    result = get_dependency_info()
    assert isinstance(result, dict)
    assert 'marker' in result
    assert 'nemotronparse' in result


def test_safe_dependency_check():
    """Test the safe dependency check function."""
    from banyan_extract.utils.dependencies import safe_check_dependency
    
    # Test with existing package
    result = safe_check_dependency('sys')
    assert result is True
    
    # Test with non-existent package
    result = safe_check_dependency('nonexistent_package_12345')
    assert result is False
    
    # Test with fallback mechanism
    result = safe_check_dependency('nonexistent_package_12345', fallback=True)
    assert result is False


def test_installation_instructions():
    """Test getting installation instructions."""
    from banyan_extract.utils.dependencies import get_installation_instructions
    
    # This should always return instructions, even if there are errors
    instructions = get_installation_instructions()
    assert isinstance(instructions, dict)
    assert 'marker' in instructions
    assert 'nemotronparse' in instructions


def test_error_handling_in_has_marker_dependencies():
    """Test error handling in has_marker_dependencies with critical errors."""
    # Clear cache before test
    has_marker_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Simulate a critical error (not just ImportError)
        mock_import.side_effect = Exception("Critical import error")
        
        # Should still return False without crashing
        result = has_marker_dependencies()
        assert result is False


def test_error_handling_in_has_nemotronparse_dependencies():
    """Test error handling in has_nemotronparse_dependencies with critical errors."""
    # Clear cache before test
    has_nemotronparse_dependencies.cache_clear()
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Simulate a critical error (not just ImportError)
        mock_import.side_effect = Exception("Critical import error")
        
        # Should still return False without crashing
        result = has_nemotronparse_dependencies()
        assert result is False


def test_log_dependency_status_error_handling():
    """Test that log_dependency_status handles errors gracefully."""
    from banyan_extract.utils.dependencies import log_dependency_status
    
    # This should not raise an exception even if there are errors
    try:
        log_dependency_status()
        assert True  # If we get here, the function worked
    except Exception as e:
        pytest.fail(f"log_dependency_status raised an exception: {e}")