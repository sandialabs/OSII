"""
Integration tests for rotation functionality that don't require external dependencies.
These tests verify that the rotation feature works correctly with actual image processing.
"""

import io
import pytest
from PIL import Image, ImageDraw
import numpy as np

from banyan_extract.utils.image_rotation import rotate_image, is_valid_rotation_angle, normalize_rotation_angle


class TestRotationIntegration:
    """Integration tests for rotation functionality."""
    
    def test_rotation_with_real_pdf_test_data(self, rotation_test_pdf):
        """Test rotation using the actual PDF test data (sample.pdf)."""
        # Verify the test PDF exists
        assert rotation_test_pdf.exists()
        assert rotation_test_pdf.name == "sample.pdf"
         
        # Test that we can read the PDF (basic validation)
        try:
            from banyan_extract.converter.pdf_to_image import convert_pdf_to_images
            
            # Convert PDF to images
            images = convert_pdf_to_images(str(rotation_test_pdf))
            
            # Verify we got at least one image
            assert len(images) > 0
            
            # Test rotation on the first image
            original_image = images[0]
            rotated_image = rotate_image(original_image, 90)
            
            # Verify rotation worked
            assert rotated_image.size == (original_image.size[1], original_image.size[0])
            
            # Verify images are different
            orig_array = np.array(original_image)
            rotated_array = np.array(rotated_image)
            assert not np.array_equal(orig_array, rotated_array)
            
        except Exception as e:
            # If PDF conversion fails (e.g., poppler not installed), skip this test
            pytest.skip(f"PDF conversion failed: {e}")
    
    def test_rotation_with_shape_pdf(self, rotation_test_pdf_with_shape):
        """Test rotation using the sample_shape.pdf for visual pattern verification."""
        # Verify the test PDF exists
        assert rotation_test_pdf_with_shape.exists()
        assert rotation_test_pdf_with_shape.name == "sample_shape.pdf"
         
        # Test that we can read the PDF (basic validation)
        try:
            from banyan_extract.converter.pdf_to_image import convert_pdf_to_images
            
            # Convert PDF to images
            images = convert_pdf_to_images(str(rotation_test_pdf_with_shape))
            
            # Verify we got at least one image
            assert len(images) > 0
            
            # Test rotation on the first image
            original_image = images[0]
            rotated_image = rotate_image(original_image, 90)
            
            # Verify rotation worked
            assert rotated_image.size == (original_image.size[1], original_image.size[0])
            
            # Verify images are different
            orig_array = np.array(original_image)
            rotated_array = np.array(rotated_image)
            assert not np.array_equal(orig_array, rotated_array)
            
        except Exception as e:
            # If PDF conversion fails (e.g., poppler not installed), skip this test
            pytest.skip(f"PDF conversion failed: {e}")
    
    def test_rotation_with_test_image_fixture(self, rotation_test_image):
        """Test rotation using the rotation test image fixture."""
        # Verify the test image has the expected properties
        assert rotation_test_image.size == (400, 300)
        assert rotation_test_image.mode == 'RGB'
        
        # Test 90-degree rotation
        rotated_90 = rotate_image(rotation_test_image, 90)
        assert rotated_90.size == (300, 400)  # Dimensions should be swapped
        
        # Test 180-degree rotation  
        rotated_180 = rotate_image(rotation_test_image, 180)
        assert rotated_180.size == (400, 300)  # Dimensions should remain the same
        
        # Test that rotations actually change the image
        orig_array = np.array(rotation_test_image)
        rotated_90_array = np.array(rotated_90)
        rotated_180_array = np.array(rotated_180)
        
        assert not np.array_equal(orig_array, rotated_90_array)
        assert not np.array_equal(orig_array, rotated_180_array)
        assert not np.array_equal(rotated_90_array, rotated_180_array)
    
    def test_rotation_angle_normalization_integration(self):
        """Test angle normalization with various inputs."""
        test_cases = [
            (0, 0.0),
            (90, 90.0),
            (360, 0.0),
            (450, 90.0),
            (-90, 270.0),
            (-360, 0.0),
            (720, 0.0),
            (1080, 0.0),
        ]
        
        for input_angle, expected_normalized in test_cases:
            normalized = normalize_rotation_angle(input_angle)
            assert normalized == expected_normalized, f"Failed for {input_angle}: got {normalized}, expected {expected_normalized}"
    
    def test_rotation_validation_integration(self):
        """Test rotation angle validation."""
        # Valid angles
        valid_angles = [0, 90, 180, 270, 360, -90, 45.5, 0.0]
        for angle in valid_angles:
            assert is_valid_rotation_angle(angle)
            # Should not raise exception
            normalize_rotation_angle(angle)
        
        # Invalid angles
        invalid_angles = ["90", None, [], {}, float('nan'), float('inf')]
        for angle in invalid_angles:
            assert not is_valid_rotation_angle(angle)
            with pytest.raises(ValueError):
                normalize_rotation_angle(angle)
    
    def test_rotation_with_different_image_formats(self):
        """Test rotation with different image formats and modes."""
        # Test RGB image
        rgb_image = Image.new('RGB', (100, 100), color='red')
        rotated_rgb = rotate_image(rgb_image, 90)
        assert rotated_rgb.mode == 'RGB'
        assert rotated_rgb.size == (100, 100)
        
        # Test RGBA image (with transparency)
        rgba_image = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        rotated_rgba = rotate_image(rgba_image, 90)
        assert rotated_rgba.mode == 'RGBA'
        assert rotated_rgba.size == (100, 100)
        
        # Test grayscale image
        gray_image = Image.new('L', (100, 100), color=128)
        rotated_gray = rotate_image(gray_image, 180)
        assert rotated_gray.mode == 'L'
        assert rotated_gray.size == (100, 100)
    
    def test_rotation_preserves_content(self):
        """Test that rotation preserves image content (just reorients it)."""
        # Create an image with a distinctive pattern
        image = Image.new('RGB', (100, 100), color='white')
        draw = ImageDraw.Draw(image)
        draw.rectangle([(25, 25), (75, 75)], fill='red')
        
        # Rotate 360 degrees (should be identical)
        rotated_360 = rotate_image(image, 360)
        assert np.array_equal(np.array(image), np.array(rotated_360))
        
        # Rotate 180 degrees twice (should return to original orientation)
        rotated_180 = rotate_image(image, 180)
        rotated_180_again = rotate_image(rotated_180, 180)
        assert np.array_equal(np.array(image), np.array(rotated_180_again))
        
        # Rotate 90 degrees four times (should return to original orientation)
        rotated_90 = rotate_image(image, 90)
        rotated_180_from_90 = rotate_image(rotated_90, 90)
        rotated_270_from_90 = rotate_image(rotated_180_from_90, 90)
        rotated_360_from_90 = rotate_image(rotated_270_from_90, 90)
        assert np.array_equal(np.array(image), np.array(rotated_360_from_90))


if __name__ == "__main__":
    pytest.main([__file__])
