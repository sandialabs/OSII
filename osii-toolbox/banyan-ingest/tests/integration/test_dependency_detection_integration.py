# Integration Tests for Dependency Detection
# This file contains integration tests for the dependency detection functionality

import pytest
import sys
from unittest.mock import patch, MagicMock

# Add the source directory to the path so we can import the module
sys.path.insert(0, '/projects/src')

from banyan_extract.utils.dependencies import (
    has_marker_dependencies,
    has_nemotronparse_dependencies,
    get_dependency_info,
    log_dependency_status,
    get_installation_instructions,
    DependencyError
)


def test_dependency_detection_integration():
    """Test basic dependency detection integration."""
    # Test that the functions can be called without errors
    marker_available = has_marker_dependencies()
    nemotronparse_available = has_nemotronparse_dependencies()
    
    # Results should be boolean
    assert isinstance(marker_available, bool)
    assert isinstance(nemotronparse_available, bool)
    
    # Test caching behavior
    marker_available_2 = has_marker_dependencies()
    nemotronparse_available_2 = has_nemotronparse_dependencies()
    
    assert marker_available == marker_available_2
    assert nemotronparse_available == nemotronparse_available_2


def test_dependency_detection_basic_functionality():
    """Test basic dependency detection functionality.
    
    This test validates that dependency detection works correctly
    by checking the actual availability of dependencies in the test environment.
    """
    # Test basic functionality
    marker_available = has_marker_dependencies()
    nemotronparse_available = has_nemotronparse_dependencies()
    
    # Debug output to understand the results
    print(f"\nDebug - Marker: {marker_available}")
    print(f"Debug - Nemotronparse: {nemotronparse_available}")
    
    # Get actual dependency information to understand the current state
    dependency_info = get_dependency_info()
    marker_pdf_available = dependency_info['marker']['marker_pdf']['available']
    surya_ocr_available = dependency_info['marker']['surya_ocr']['available']
    openai_available = dependency_info['nemotronparse']['openai']['available']
    
    print(f"Actual dependency availability - marker_pdf: {marker_pdf_available}, surya_ocr: {surya_ocr_available}, openai: {openai_available}")
    
    # Test logic based on actual dependency availability
    if not marker_pdf_available or not surya_ocr_available:
        # If marker dependencies are not available, should return False
        assert marker_available is False, "Marker dependencies should be reported as unavailable"
   
    if not openai_available:
        # If nemotronparse dependencies are not available, should return False
        assert nemotronparse_available is False, "Nemotronparse dependencies should be reported as unavailable"
     
    # For available dependencies, should return True
    if marker_pdf_available and surya_ocr_available:
        assert marker_available is True, "Marker dependencies should be reported as available"
    
    if openai_available:
        assert nemotronparse_available is True, "Nemotronparse dependencies should be reported as available"
    
    # Verify that the results match the actual dependency availability
    assert marker_available == (marker_pdf_available and surya_ocr_available)
    assert nemotronparse_available == openai_available


def test_dependency_info_structure():
    """Test that get_dependency_info returns the expected structure."""
    dependency_info = get_dependency_info()
    
    # Check that the result has the expected structure
    assert isinstance(dependency_info, dict)
    assert 'marker' in dependency_info
    assert 'nemotronparse' in dependency_info
    
    # Check marker dependencies
    marker_deps = dependency_info['marker']
    assert 'marker_pdf' in marker_deps
    assert 'surya_ocr' in marker_deps
    
    # Check nemotronparse dependencies
    nemotronparse_deps = dependency_info['nemotronparse']
    assert 'openai' in nemotronparse_deps
    
    # Check that each package has the expected fields
    for package_name, package_info in marker_deps.items():
        assert 'available' in package_info
        assert 'version' in package_info
        assert 'error' in package_info
        assert isinstance(package_info['available'], bool)
    
    for package_name, package_info in nemotronparse_deps.items():
        assert 'available' in package_info
        assert 'version' in package_info
        assert 'error' in package_info
        assert isinstance(package_info['available'], bool)


def test_log_dependency_status():
    """Test that log_dependency_status runs without errors."""
    # This should not raise an exception
    try:
        log_dependency_status()
        assert True  # If we get here, the function worked
    except Exception as e:
        pytest.fail(f"log_dependency_status raised an exception: {e}")


def test_caching_behavior_integration():
    """Test that caching works correctly in integration context."""
    # Clear cache first
    has_marker_dependencies.cache_clear()
    has_nemotronparse_dependencies.cache_clear()
    
    # First calls
    marker_1 = has_marker_dependencies()
    nemotronparse_1 = has_nemotronparse_dependencies()
    
    # Second calls should use cache
    marker_2 = has_marker_dependencies()
    nemotronparse_2 = has_nemotronparse_dependencies()
    
    # Results should be identical
    assert marker_1 == marker_2
    assert nemotronparse_1 == nemotronparse_2


def test_error_handling_integration():
    """Test error handling in integration context."""
    # Test that functions handle errors gracefully
    
    # Test with mocked import errors
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock ImportError for all packages
        mock_import.side_effect = ImportError("Mocked import error")
        
        # Clear cache to ensure fresh calls
        has_marker_dependencies.cache_clear()
        has_nemotronparse_dependencies.cache_clear()
        
        # Should return False without crashing
        marker_result = has_marker_dependencies()
        nemotronparse_result = has_nemotronparse_dependencies()
        
        assert marker_result is False
        assert nemotronparse_result is False


def test_safe_dependency_check_integration():
    """Test safe_dependency_check in integration context."""
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


def test_installation_instructions_integration():
    """Test getting installation instructions in integration context."""
    instructions = get_installation_instructions()
    
    # Should always return instructions
    assert isinstance(instructions, dict)
    assert 'marker' in instructions
    assert 'nemotronparse' in instructions


def test_error_recovery_integration():
    """Test error recovery in integration context."""
    # Test that functions can recover from errors
    
    # Test get_dependency_info with mocked errors
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock various types of errors
        mock_import.side_effect = Exception("Unexpected error")
        
        # Should handle the error gracefully
        dependency_info = get_dependency_info()
        
        # Should still return a valid structure
        assert isinstance(dependency_info, dict)
        assert 'marker' in dependency_info
        assert 'nemotronparse' in dependency_info


def test_dependency_info_completeness():
    """Test that dependency info is complete and consistent."""
    dependency_info = get_dependency_info()
    
    # Check that all expected packages are present
    expected_packages = ['marker_pdf', 'surya_ocr', 'openai']
    
    all_packages = []
    for group in dependency_info.values():
        all_packages.extend(group.keys())
    
    for package in expected_packages:
        assert package in all_packages, f"Expected package {package} not found in dependency info"


def test_dependency_consistency():
    """Test that dependency detection is consistent across multiple calls."""
    # Clear cache
    has_marker_dependencies.cache_clear()
    has_nemotronparse_dependencies.cache_clear()
    
    # Make multiple calls
    results = []
    for i in range(3):
        marker = has_marker_dependencies()
        nemotronparse = has_nemotronparse_dependencies()
        results.append((marker, nemotronparse))
    
    # All results should be identical
    for result in results:
        assert result == results[0], "Dependency detection results should be consistent"


def test_error_handling_with_critical_errors():
    """Test error handling with critical errors."""
    # Test that functions handle critical errors gracefully
    
    with patch('banyan_extract.utils.dependencies.importlib.import_module') as mock_import:
        # Mock a critical error
        mock_import.side_effect = Exception("Critical error")
        
        # Clear cache
        has_marker_dependencies.cache_clear()
        has_nemotronparse_dependencies.cache_clear()
        
        # Should return False without crashing
        marker_result = has_marker_dependencies()
        nemotronparse_result = has_nemotronparse_dependencies()
        
        assert marker_result is False
        assert nemotronparse_result is False