# Test cases for rotation detection functionality

import pytest
from unittest.mock import patch, MagicMock, Mock
from PIL import Image
import numpy as np

# Import the functions to test
from banyan_extract.utils.rotation_detection import (
    detect_rotation_angle,
    detect_rotation_angle_with_fallback,
    RotationDetectionError,
    TesseractNotFoundError,
    InvalidImageError
)


class TestValidateImage:
    """Test cases for image validation through public API."""
    
    def test_validate_image_valid(self):
        """Test that valid images pass validation through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        # Mock pytesseract to avoid actual OCR call
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            # Should not raise exception for valid image
            angle = detect_rotation_angle(image)
            assert angle == 0.0
    
    def test_validate_image_none(self):
        """Test that None image raises InvalidImageError through detect_rotation_angle."""
        with pytest.raises(InvalidImageError, match="Image cannot be None"):
            detect_rotation_angle(None)
    
    def test_validate_image_invalid_type(self):
        """Test that non-Image objects raise InvalidImageError through detect_rotation_angle."""
        with pytest.raises(InvalidImageError, match="Image must be a PIL Image object"):
            detect_rotation_angle("not_an_image")
        
        with pytest.raises(InvalidImageError, match="Image must be a PIL Image object"):
            detect_rotation_angle(123)
        
        with pytest.raises(InvalidImageError, match="Image must be a PIL Image object"):
            detect_rotation_angle([1, 2, 3])


class TestPreprocessImageForOSD:
    """Test cases for image preprocessing through public API."""
    
    def test_preprocess_rgb_image(self):
        """Test preprocessing of RGB image through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract to capture the processed image
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image)
            
            # Verify the function was called (which means preprocessing succeeded)
            mock_pytesseract.image_to_osd.assert_called_once()
            assert angle == 0.0
    
    def test_preprocess_rgba_image(self):
        """Test preprocessing of RGBA image through detect_rotation_angle."""
        image = Image.new('RGBA', (100, 100), color=(255, 255, 255, 128))
        
        # Mock pytesseract to capture the processed image
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image)
            
            # Verify the function was called (which means preprocessing succeeded)
            mock_pytesseract.image_to_osd.assert_called_once()
            assert angle == 0.0
    
    def test_preprocess_grayscale_image(self):
        """Test preprocessing of grayscale image through detect_rotation_angle."""
        image = Image.new('L', (100, 100), color=128)
        
        # Mock pytesseract to capture the processed image
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image)
            
            # Verify the function was called (which means preprocessing succeeded)
            mock_pytesseract.image_to_osd.assert_called_once()
            assert angle == 0.0
    
    def test_preprocess_cmyk_image(self):
        """Test preprocessing of CMYK image through detect_rotation_angle."""
        image = Image.new('CMYK', (100, 100), color=(0, 0, 0, 0))
        
        # Mock pytesseract to capture the processed image
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image)
            
            # Verify the function was called (which means preprocessing succeeded)
            mock_pytesseract.image_to_osd.assert_called_once()
            assert angle == 0.0


class TestParseOSDOutput:
    """Test cases for OSD output parsing through public API."""
    
    def test_parse_valid_osd_output(self):
        """Test parsing of valid OSD output through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with valid output
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 90.0
    
    def test_parse_osd_output_missing_orientation(self):
        """Test parsing of OSD output missing orientation field through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with missing orientation
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            with pytest.raises(RotationDetectionError, match="OSD output missing 'orientation' field"):
                detect_rotation_angle(image)
    
    def test_parse_osd_output_missing_confidence(self):
        """Test parsing of OSD output missing confidence field through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with missing confidence
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            # Should work with default confidence of 0.0, but fail threshold check
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 0.0  # Should return 0 due to low confidence
    
    def test_parse_osd_output_invalid_values(self):
        """Test parsing of OSD output with invalid values through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with invalid values
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': 'invalid',
            'orientation_conf': 'invalid'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            with pytest.raises(RotationDetectionError, match="Failed to parse OSD output"):
                detect_rotation_angle(image)
    
    def test_parse_osd_output_zero_confidence(self):
        """Test parsing of OSD output with zero confidence through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with zero confidence
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.0'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 0.0  # Should return 0 due to low confidence
    
    def test_parse_osd_output_high_confidence(self):
        """Test parsing of OSD output with high confidence through detect_rotation_angle."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with high confidence
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.95'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 180.0


class TestDetectRotationAngle:
    """Test cases for detect_rotation_angle function."""
    
    def test_detect_rotation_angle_none_image(self):
        """Test that None image raises InvalidImageError."""
        with pytest.raises(InvalidImageError, match="Image cannot be None"):
            detect_rotation_angle(None)
    
    def test_detect_rotation_angle_invalid_image(self):
        """Test that invalid image raises InvalidImageError."""
        with pytest.raises(InvalidImageError, match="Image must be a PIL Image object"):
            detect_rotation_angle("not_an_image")
    
    def test_detect_rotation_angle_tesseract_not_available(self):
        """Test behavior when Tesseract dependencies are not available."""
        image = Image.new('RGB', (100, 100), color='white')
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            with pytest.raises(TesseractNotFoundError, match="Tesseract OCR dependencies are not available"):
                detect_rotation_angle(image)
    
    def test_detect_rotation_angle_success_high_confidence(self):
        """Test successful rotation detection with high confidence."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 90.0
    
    def test_detect_rotation_angle_success_low_confidence(self):
        """Test rotation detection with confidence below threshold."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.65'  # Below 0.7 threshold
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 0.0  # Should return 0 due to low confidence
    
    def test_detect_rotation_angle_zero_rotation(self):
        """Test rotation detection when no rotation is needed."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 0.0
    
    def test_detect_rotation_angle_180_rotation(self):
        """Test rotation detection for 180-degree rotation."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 180.0
    
    def test_detect_rotation_angle_270_rotation(self):
        """Test rotation detection for 270-degree rotation."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '270',
            'orientation_conf': '0.92'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 270.0
    
    def test_detect_rotation_angle_pytesseract_import_error(self):
        """Test behavior when pytesseract import fails."""
        image = Image.new('RGB', (100, 100), color='white')
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': None}):
            
            with pytest.raises(TesseractNotFoundError, match="pytesseract import failed"):
                detect_rotation_angle(image)
    
    def test_detect_rotation_angle_tesseract_not_found_error(self):
        """Test behavior when Tesseract binary is not found."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with TesseractNotFoundError
        mock_pytesseract = MagicMock()
        mock_pytesseract.TesseractNotFoundError = Exception
        mock_pytesseract.image_to_osd.side_effect = mock_pytesseract.TesseractNotFoundError("Tesseract not found")
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            with pytest.raises(TesseractNotFoundError, match="Tesseract OCR binary not found"):
                detect_rotation_angle(image)


    def test_detect_rotation_angle_tesseract_error(self):
        """Test behavior when Tesseract OCR error occurs."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with TesseractError
        mock_pytesseract = MagicMock()
        
        # Create a proper exception class
        class MockTesseractError(Exception):
            pass
        
        mock_pytesseract.TesseractError = MockTesseractError
        mock_pytesseract.image_to_osd.side_effect = MockTesseractError("OCR error")
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            with pytest.raises(RotationDetectionError, match="Rotation detection failed"):
                detect_rotation_angle(image)


    def test_detect_rotation_angle_invalid_osd_output(self):
        """Test behavior when OSD output is invalid."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract with invalid output
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {}
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # This should raise RotationDetectionError due to invalid OSD output
            # But the error handling should catch it properly
            with pytest.raises(RotationDetectionError):
                detect_rotation_angle(image)


    def test_detect_rotation_angle_custom_config(self):
        """Test rotation detection with custom pytesseract config."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        custom_config = '--psm 6 --oem 3'
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image, pytesseract_config=custom_config)
            
            # Verify that the custom config was passed to pytesseract
            mock_pytesseract.image_to_osd.assert_called_once()
            call_args = mock_pytesseract.image_to_osd.call_args
            assert call_args[1]['config'] == custom_config
            
            assert angle == 90.0


class TestDetectRotationAngleWithFallback:
    """Test cases for detect_rotation_angle_with_fallback function."""
    
    def test_fallback_success(self):
        """Test successful rotation detection with fallback function."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Mock pytesseract and its functions
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 90.0
    
    def test_fallback_tesseract_not_available(self):
        """Test fallback when Tesseract dependencies are not available."""
        image = Image.new('RGB', (100, 100), color='white')
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 0.0
    
    def test_fallback_exception(self):
        """Test fallback when any exception occurs."""
        image = Image.new('RGB', (100, 100), color='white')
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': MagicMock(side_effect=Exception("Unexpected error"))}):
            
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 0.0
    
    def test_fallback_invalid_image(self):
        """Test fallback when image is invalid."""
        angle = detect_rotation_angle_with_fallback("not_an_image")
        assert angle == 0.0





class TestRotationDetectionEdgeCases:
    """Test edge cases for rotation detection."""
    
    def test_very_small_image(self):
        """Test rotation detection on very small image."""
        image = Image.new('RGB', (10, 10), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '0',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image)
            assert angle == 0.0
    
    def test_large_image(self):
        """Test rotation detection on large image."""
        image = Image.new('RGB', (2000, 2000), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image)
            assert angle == 180.0
    
    def test_rgba_image_with_transparency(self):
        """Test rotation detection on RGBA image with transparency."""
        image = Image.new('RGBA', (100, 100), color=(255, 255, 255, 0))
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '270',
            'orientation_conf': '0.88'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image)
            assert angle == 270.0
    
    def test_grayscale_image(self):
        """Test rotation detection on grayscale image."""
        image = Image.new('L', (100, 100), color=128)
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.82'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            angle = detect_rotation_angle(image)
            assert angle == 90.0
    
    def test_custom_confidence_thresholds(self):
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


if __name__ == "__main__":
    pytest.main([__file__])