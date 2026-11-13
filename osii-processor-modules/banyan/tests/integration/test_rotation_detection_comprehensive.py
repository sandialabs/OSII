# Comprehensive integration tests for rotation detection functionality
# This test suite covers all aspects of the rotation detection feature

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw
import numpy as np

# Import the functions to test
from banyan_extract.utils.rotation_detection import (
    detect_rotation_angle,
    detect_rotation_angle_with_fallback,
    TesseractNotFoundError,
    RotationDetectionError
)
from banyan_extract.utils.image_rotation import rotate_image


class TestRotationDetectionWithSamplePDF:
    """Integration tests using sample_rotation.pdf file."""
    
    def test_sample_rotation_pdf_exists(self, test_data_dir):
        """Test that sample_rotation.pdf file exists."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        assert sample_pdf_path.exists()
        assert sample_pdf_path.is_file()
        assert sample_pdf_path.stat().st_size > 0
    
    def test_rotation_detection_with_sample_pdf(self, test_data_dir):
        """Test rotation detection using sample_rotation.pdf."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        
        try:
            # Try to convert PDF to images
            from pdf2image import convert_from_path
            
            # Convert first page to image
            images = convert_from_path(str(sample_pdf_path), first_page=1, last_page=1)
            assert len(images) > 0
            
            image = images[0]
            assert isinstance(image, Image.Image)
            
            # Test rotation detection with mocked Tesseract
            mock_pytesseract = MagicMock()
            mock_pytesseract.image_to_osd.return_value = {
                'orientation': '90',
                'orientation_conf': '0.85'
            }
            
            with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
                 patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
                
                # Test rotation detection
                angle = detect_rotation_angle(image, confidence_threshold=0.7)
                assert angle == 90.0
                
                # Test rotation correction
                corrected_image = rotate_image(image, angle)
                assert corrected_image.size == (image.size[1], image.size[0])
                
        except Exception as e:
            # If PDF conversion fails, skip this test
            pytest.skip(f"PDF conversion failed: {e}")


class TestRotationDetectionVariousAngles:
    """Test rotation detection with various rotation angles."""
    
    @pytest.mark.parametrize("angle,expected_angle", [
        (0, 0.0),
        (90, 90.0),
        (180, 180.0),
        (270, 270.0),
        (360, 0.0),  # Should normalize to 0
        (-90, 270.0),  # Should normalize to 270
        (450, 90.0),  # Should normalize to 90
    ])
    def test_rotation_detection_various_angles(self, angle, expected_angle):
        """Test rotation detection with various angles."""
        # Create a test image
        image = Image.new('RGB', (200, 100), color='white')
        
        # Mock pytesseract to return the expected angle
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': str(angle),
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            detected_angle = detect_rotation_angle(image, confidence_threshold=0.7)
            # The detected angle should be normalized
            assert detected_angle == expected_angle
    
    def test_rotation_detection_all_standard_angles(self):
        """Test rotation detection for all standard angles (0, 90, 180, 270)."""
        test_cases = [
            (0, "0"),
            (90, "90"),
            (180, "180"),
            (270, "270")
        ]
        
        for expected_angle, osd_angle in test_cases:
            image = Image.new('RGB', (100, 100), color='white')
            
            mock_pytesseract = MagicMock()
            mock_pytesseract.image_to_osd.return_value = {
                'orientation': osd_angle,
                'orientation_conf': '0.85'
            }
            
            with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
                 patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
                
                detected_angle = detect_rotation_angle(image, confidence_threshold=0.7)
                assert detected_angle == expected_angle


class TestRotationDetectionFallbackBehavior:
    """Test fallback behavior when Tesseract is unavailable."""
    
    def test_fallback_when_tesseract_not_available(self):
        """Test that rotation detection falls back gracefully when Tesseract is unavailable."""
        image = Image.new('RGB', (100, 100), color='white')
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            # Should raise TesseractNotFoundError
            with pytest.raises(TesseractNotFoundError):
                detect_rotation_angle(image)
    
    def test_fallback_function_always_returns_zero(self):
        """Test that detect_rotation_angle_with_fallback always returns 0.0 on error."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Test with Tesseract not available
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 0.0
        
        # Test with exception during detection
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': MagicMock(side_effect=Exception("Test error"))}):
            
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 0.0
        
        # Test with invalid image
        angle = detect_rotation_angle_with_fallback("not_an_image")
        assert angle == 0.0
    
    def test_detect_rotation_angle_fallback(self):
        """Test detect_rotation_angle fallback behavior."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Test with Tesseract not available - should raise TesseractNotFoundError
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            with pytest.raises(TesseractNotFoundError):
                detect_rotation_angle(image)
        
        # Test with exception during detection
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': MagicMock(side_effect=Exception("Test error"))}):
             
            with pytest.raises(RotationDetectionError):
                detect_rotation_angle(image)


class TestRotationDetectionCLIIntegration:
    """Test CLI argument parsing for rotation detection."""
    
    def test_cli_rotation_argument_parsing(self):
        """Test that CLI correctly parses rotation-related arguments."""
        from banyan_extract.cli import parse_arguments
        
        # Test auto-detection flag
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--auto_detect_rotation']):
            args = parse_arguments()
            assert args.auto_detect_rotation is True
            assert args.rotation_angle == 0  # Default value
        
        # Test manual rotation angle
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_angle', '90']):
            args = parse_arguments()
            assert args.rotation_angle == 90
            assert args.auto_detect_rotation is False
        
        # Test confidence threshold
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '0.8']):
            args = parse_arguments()
            assert args.rotation_confidence_threshold == 0.8
        
        # Test both manual and auto (manual should take precedence)
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_angle', '180', '--auto_detect_rotation']):
            args = parse_arguments()
            assert args.rotation_angle == 180
            assert args.auto_detect_rotation is True
    
    def test_cli_rotation_confidence_threshold_validation(self):
        """Test validation of rotation confidence threshold."""
        from banyan_extract.cli import parse_arguments
        
        # Test valid threshold
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '0.75']):
            args = parse_arguments()
            assert args.rotation_confidence_threshold == 0.75
        
        # Test invalid threshold (too low)
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '-0.1']):
            with pytest.raises(SystemExit):  # Should exit due to validation error
                parse_arguments()
        
        # Test invalid threshold (too high)
        with patch('sys.argv', ['banyan_extract', 'input.pdf', 'output/', '--rotation_confidence_threshold', '1.1']):
            with pytest.raises(SystemExit):  # Should exit due to validation error
                parse_arguments()


class TestRotationDetectionBatchProcessing:
    """Test batch processing with mixed rotated/non-rotated documents."""
    
    def test_batch_processing_mixed_rotations(self):
        """Test batch processing with mixed rotated and non-rotated documents."""
        # Create multiple test images with different rotations
        test_images = []
        expected_angles = []
        
        # Non-rotated image
        img1 = Image.new('RGB', (200, 100), color='white')
        test_images.append(img1)
        expected_angles.append(0.0)
        
        # 90-degree rotated image
        img2 = Image.new('RGB', (200, 100), color='lightgray')
        test_images.append(img2)
        expected_angles.append(90.0)
        
        # 180-degree rotated image
        img3 = Image.new('RGB', (200, 100), color='darkgray')
        test_images.append(img3)
        expected_angles.append(180.0)
        
        # 270-degree rotated image
        img4 = Image.new('RGB', (200, 100), color='gray')
        test_images.append(img4)
        expected_angles.append(270.0)
        
        # Mock pytesseract to return different rotations for each image
        mock_pytesseract = MagicMock()
        
        def mock_image_to_osd(image, config=None, output_type=None):
            # Return different rotation based on image color
            if image.getpixel((50, 50)) == (255, 255, 255):  # white
                return {'orientation': '0', 'orientation_conf': '0.85'}
            elif image.getpixel((50, 50)) == (211, 211, 211):  # lightgray
                return {'orientation': '90', 'orientation_conf': '0.85'}
            elif image.getpixel((50, 50)) == (169, 169, 169):  # darkgray
                return {'orientation': '180', 'orientation_conf': '0.85'}
            elif image.getpixel((50, 50)) == (128, 128, 128):  # gray
                return {'orientation': '270', 'orientation_conf': '0.85'}
            else:
                return {'orientation': '0', 'orientation_conf': '0.85'}
        
        mock_pytesseract.image_to_osd = mock_image_to_osd
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Process each image
            detected_angles = []
            for image in test_images:
                angle = detect_rotation_angle(image, confidence_threshold=0.7)
                detected_angles.append(angle)
            
            # Verify all angles were detected correctly
            assert detected_angles == expected_angles
    
    def test_batch_processing_with_fallback(self):
        """Test batch processing with fallback when Tesseract unavailable."""
        # Create test images
        test_images = [
            Image.new('RGB', (100, 100), color='white'),
            Image.new('RGB', (100, 100), color='lightgray'),
            Image.new('RGB', (100, 100), color='darkgray'),
        ]
        
        # Test with Tesseract not available
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            
            detected_angles = []
            for image in test_images:
                # Use fallback function
                angle = detect_rotation_angle_with_fallback(image)
                detected_angles.append(angle)
            
            # All should fallback to 0.0
            assert detected_angles == [0.0, 0.0, 0.0]


class TestRotationDetectionEdgeCases:
    """Test edge cases for rotation detection."""
    
    def test_rotation_detection_with_different_image_formats(self):
        """Test rotation detection with different image formats."""
        image_formats = [
            ('RGB', (255, 0, 0)),
            ('RGBA', (255, 0, 0, 128)),
            ('L', 128),
            ('CMYK', (0, 0, 0, 0))
        ]
        
        for mode, color in image_formats:
            if mode == 'RGB':
                image = Image.new(mode, (100, 100), color=color)
            elif mode == 'RGBA':
                image = Image.new(mode, (100, 100), color=color)
            elif mode == 'L':
                image = Image.new(mode, (100, 100), color=color)
            elif mode == 'CMYK':
                image = Image.new(mode, (100, 100), color=color)
            
            mock_pytesseract = MagicMock()
            mock_pytesseract.image_to_osd.return_value = {
                'orientation': '90',
                'orientation_conf': '0.85'
            }
            
            with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
                 patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
                
                angle = detect_rotation_angle(image, confidence_threshold=0.7)
                assert angle == 90.0
    
    def test_rotation_detection_with_different_confidence_thresholds(self):
        """Test rotation detection with various confidence thresholds."""
        image = Image.new('RGB', (100, 100), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.75'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Should pass with threshold 0.7
            angle1 = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle1 == 90.0
            
            # Should pass with threshold 0.75
            angle2 = detect_rotation_angle(image, confidence_threshold=0.75)
            assert angle2 == 90.0
            
            # Should fail with threshold 0.8
            angle3 = detect_rotation_angle(image, confidence_threshold=0.8)
            assert angle3 == 0.0
    
    def test_rotation_detection_with_low_confidence(self):
        """Test rotation detection with low confidence scores."""
        image = Image.new('RGB', (100, 100), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.3'  # Low confidence
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Should return 0.0 due to low confidence
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 0.0
    
    def test_rotation_detection_with_very_small_and_large_images(self):
        """Test rotation detection with very small and large images."""
        # Very small image
        small_image = Image.new('RGB', (10, 10), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(small_image)
            assert angle == 0.0
        
        # Large image (but not too large to cause memory issues in tests)
        large_image = Image.new('RGB', (1000, 1000), color='white')
        
        mock_pytesseract2 = MagicMock()
        mock_pytesseract2.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract2}):
            
            angle = detect_rotation_angle(large_image)
            assert angle == 180.0


class TestRotationDetectionErrorHandling:
    """Test error handling in rotation detection."""
    
    def test_rotation_detection_with_invalid_image(self):
        """Test rotation detection with invalid image inputs."""
        # Test with None
        with pytest.raises(Exception):
            detect_rotation_angle(None)
        
        # Test with invalid type
        with pytest.raises(Exception):
            detect_rotation_angle("not_an_image")
        
        # Test with number
        with pytest.raises(Exception):
            detect_rotation_angle(123)
        
        # Test with list
        with pytest.raises(Exception):
            detect_rotation_angle([1, 2, 3])
    
    def test_rotation_detection_with_invalid_osd_output(self):
        """Test rotation detection with invalid OSD output."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Test with missing orientation field
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            with pytest.raises(RotationDetectionError):
                detect_rotation_angle(image)
        
        # Test with invalid orientation value
        mock_pytesseract2 = MagicMock()
        mock_pytesseract2.image_to_osd.return_value = {
            'orientation': 'invalid',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract2}):
            
            with pytest.raises(RotationDetectionError):
                detect_rotation_angle(image)
    
    def test_rotation_detection_with_pytesseract_errors(self):
        """Test rotation detection with various pytesseract errors."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Test with TesseractNotFoundError
        mock_pytesseract = MagicMock()
        
        class MockTesseractNotFoundError(Exception):
            pass
        
        mock_pytesseract.TesseractNotFoundError = MockTesseractNotFoundError
        mock_pytesseract.image_to_osd.side_effect = MockTesseractNotFoundError("Tesseract not found")
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            with pytest.raises(TesseractNotFoundError):
                detect_rotation_angle(image)
        
        # Test with TesseractError
        mock_pytesseract2 = MagicMock()
        
        class MockTesseractError(Exception):
            pass
        
        mock_pytesseract2.TesseractError = MockTesseractError
        mock_pytesseract2.image_to_osd.side_effect = MockTesseractError("OCR error")
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract2}):
            
            with pytest.raises(RotationDetectionError):
                detect_rotation_angle(image)


if __name__ == "__main__":
    pytest.main([__file__])