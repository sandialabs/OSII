# Integration tests for rotation detection functionality

import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

# Import the functions to test
from banyan_extract.utils.rotation_detection import (
    detect_rotation_angle,
    detect_rotation_angle_with_fallback,
    RotationDetectionError,
    TesseractNotFoundError,
    InvalidImageError
)
from banyan_extract.utils.image_rotation import rotate_image


class TestRotationDetectionIntegration:
    """Integration tests for rotation detection with image rotation."""
    
    def test_full_rotation_correction_workflow(self):
        """Test the complete rotation detection and correction workflow."""
        # Create a test image
        image = Image.new('RGB', (200, 100), color='white')
        
        # Mock pytesseract to detect 90-degree rotation
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Step 1: Detect rotation
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 90.0
            
            # Step 2: Rotate the image to correct orientation
            corrected_image = rotate_image(image, angle)
            
            # Step 3: Verify the rotation
            assert corrected_image.size == (100, 200)  # Dimensions should be swapped for 90-degree rotation
    
    def test_rotation_correction_with_fallback(self):
        """Test rotation correction with automatic fallback."""
        image = Image.new('RGB', (100, 100), color='white')
        
        # Test with Tesseract not available
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
            angle = detect_rotation_angle_with_fallback(image)
            assert angle == 0.0  # Should fallback to 0 degrees
            
            # No rotation should be applied
            corrected_image = rotate_image(image, angle)
            assert corrected_image.size == image.size
    
    def test_get_rotation_info_and_correct(self):
        """Test getting rotation info and applying correction."""
        image = Image.new('RGB', (100, 200), color='white')
        
        # Mock pytesseract to detect 180-degree rotation
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
             
            # Get rotation angle using detect_rotation_angle
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            
            # Verify the angle
            assert angle == 180.0
            
            # Apply correction if needed
            if angle != 0:
                corrected_image = rotate_image(image, angle)
                assert corrected_image.size == image.size  # 180-degree rotation maintains dimensions
    
    def test_multiple_rotation_detections(self):
        """Test multiple rotation detections on different images."""
        test_cases = [
            (90, '90'),
            (180, '180'),
            (270, '270'),
            (0, '0')
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
    
    def test_rotation_detection_with_different_image_types(self):
        """Test rotation detection with different image types."""
        image_types = [
            ('RGB', (255, 0, 0)),
            ('RGBA', (255, 0, 0, 128)),
            ('L', 128)
        ]
        
        for mode, color in image_types:
            if mode == 'RGB':
                image = Image.new(mode, (100, 100), color=color)
            elif mode == 'RGBA':
                image = Image.new(mode, (100, 100), color=color)
            else:  # Grayscale
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


if __name__ == "__main__":
    pytest.main([__file__])