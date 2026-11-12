# Unit tests for CLI argument parsing related to rotation detection

import pytest
from unittest.mock import patch, MagicMock
import sys

from banyan_extract.cli import parse_arguments, validate_rotation_confidence_threshold


class TestRotationCLIArguments:
    """Test CLI argument parsing for rotation-related features."""
    
    def test_auto_detect_rotation_flag(self):
        """Test --auto_detect_rotation flag parsing."""
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--auto_detect_rotation']):
            args = parse_arguments()
            assert args.auto_detect_rotation is True
            assert args.rotation_angle == 0  # Default value
    
    def test_manual_rotation_angle(self):
        """Test --rotation_angle argument parsing."""
        test_angles = [0, 90, 180, 270, 45, 360, -90]
        
        for angle in test_angles:
            with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_angle', str(angle)]):
                args = parse_arguments()
                assert args.rotation_angle == angle
                assert args.auto_detect_rotation is False
    
    def test_rotation_confidence_threshold(self):
        """Test --rotation_confidence_threshold argument parsing."""
        test_thresholds = [0.0, 0.5, 0.7, 0.9, 1.0]
        
        for threshold in test_thresholds:
            with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', str(threshold)]):
                args = parse_arguments()
                assert args.rotation_confidence_threshold == threshold
    
    def test_both_manual_and_auto_rotation(self):
        """Test behavior when both manual rotation and auto detection are specified."""
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_angle', '180', '--auto_detect_rotation']):
            args = parse_arguments()
            assert args.rotation_angle == 180
            assert args.auto_detect_rotation is True
    
    def test_default_rotation_values(self):
        """Test default rotation values when no rotation arguments are provided."""
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/']):
            args = parse_arguments()
            assert args.rotation_angle == 0
            assert args.auto_detect_rotation is False
            assert args.rotation_confidence_threshold == 0.7


class TestRotationConfidenceThresholdValidation:
    """Test validation of rotation confidence threshold."""
    
    def test_valid_thresholds(self):
        """Test that valid thresholds pass validation."""
        valid_thresholds = [0.0, 0.1, 0.5, 0.7, 0.9, 1.0]
        
        for threshold in valid_thresholds:
            # Should not raise exception
            validate_rotation_confidence_threshold(threshold)
    
    def test_invalid_thresholds(self):
        """Test that invalid thresholds raise ValueError."""
        invalid_thresholds = [-0.1, -1.0, 1.1, 2.0, float('inf'), float('-inf')]
        
        for threshold in invalid_thresholds:
            with pytest.raises(ValueError, match="rotation_confidence_threshold must be between 0.0 and 1.0"):
                validate_rotation_confidence_threshold(threshold)
    
    def test_non_numeric_thresholds(self):
        """Test that non-numeric thresholds are handled by argparse."""
        # The validation function only checks numeric range, not type
        # argparse will handle type conversion, so we test that here
        
        # Test string that can be converted to float
        result = validate_rotation_confidence_threshold(0.5)  # This should work
        assert result is None  # Function doesn't return anything, just validates
        
        # Test that invalid numeric values still raise ValueError
        with pytest.raises(ValueError):
            validate_rotation_confidence_threshold(-0.1)


class TestRotationCLIErrorHandling:
    """Test error handling in CLI argument parsing for rotation."""
    
    def test_invalid_rotation_confidence_threshold_cli(self):
        """Test that invalid rotation confidence threshold causes CLI to exit."""
        # Test threshold below minimum
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '-0.1']):
            with pytest.raises(SystemExit):
                parse_arguments()
        
        # Test threshold above maximum
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '1.1']):
            with pytest.raises(SystemExit):
                parse_arguments()
        
        # Test non-numeric threshold
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', 'invalid']):
            with pytest.raises(SystemExit):
                parse_arguments()
    
    def test_invalid_rotation_angle_cli(self):
        """Test that invalid rotation angle causes appropriate error."""
        # Test non-numeric rotation angle
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_angle', 'invalid']):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestRotationCLITesseractDependencyChecking:
    """Test Tesseract dependency checking in CLI."""
    
    def test_tesseract_dependency_checking_when_auto_detect_enabled(self):
        """Test that CLI checks Tesseract dependencies when auto-detection is enabled."""
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--auto_detect_rotation']):
            # Mock the dependency checking by patching the import
            with patch('banyan_extract.utils.tesseract_dependencies.has_tesseract_dependencies', return_value=False):
                # Should not raise exception, but should log warnings
                args = parse_arguments()
                assert args.auto_detect_rotation is True
    
    def test_tesseract_dependency_checking_when_disabled(self):
        """Test that CLI doesn't check Tesseract dependencies when auto-detection is disabled."""
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/']):
            # Should not check Tesseract dependencies
            args = parse_arguments()
            assert args.auto_detect_rotation is False


class TestRotationCLIIntegration:
    """Integration tests for rotation CLI functionality."""
    
    def test_rotation_arguments_with_different_backends(self):
        """Test rotation arguments work with different backends."""
        backends = ['nemoparse', 'marker', 'pptx']
        
        for backend in backends:
            with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--backend', backend, '--auto_detect_rotation']):
                args = parse_arguments()
                assert args.backend == backend
                assert args.auto_detect_rotation is True
    
    def test_rotation_arguments_with_batch_processing(self):
        """Test rotation arguments with batch processing."""
        with patch('sys.argv', ['banyan_extract', 'input_dir/', 'output/', '--is_input_dir', '--auto_detect_rotation', '--rotation_confidence_threshold', '0.8']):
            args = parse_arguments()
            assert args.is_input_dir is True
            assert args.auto_detect_rotation is True
            assert args.rotation_confidence_threshold == 0.8
    
    def test_rotation_arguments_with_other_options(self):
        """Test rotation arguments combined with other CLI options."""
        with patch('sys.argv', [
            'banyan_extract', 'input.pdf', 'output/',
            '--auto_detect_rotation',
            '--draw_bboxes',
            '--sort_by_position',
            '--rotation_confidence_threshold', '0.75'
        ]):
            args = parse_arguments()
            assert args.auto_detect_rotation is True
            assert args.draw_bboxes is True
            assert args.sort_by_position is True
            assert args.rotation_confidence_threshold == 0.75


if __name__ == "__main__":
    pytest.main([__file__])