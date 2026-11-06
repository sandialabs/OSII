"""
Test cases for the image rotation utility functions.
"""

import pytest
from PIL import Image, ImageDraw
import numpy as np
from banyan_extract.utils.image_rotation import (
    rotate_image,
    is_valid_rotation_angle,
    normalize_rotation_angle
)


class TestImageRotation:
    """Test cases for rotate_image function."""
    
    def test_rotate_image_none(self):
        """Test that rotate_image raises ValueError for None image."""
        with pytest.raises(ValueError, match="Image cannot be None"):
            rotate_image(None, 90)
    
    def test_rotate_image_invalid_type(self):
        """Test that rotate_image raises TypeError for invalid image type."""
        with pytest.raises(TypeError, match="Image must be a PIL Image object"):
            rotate_image("not_an_image", 90)
    
    def test_rotate_image_invalid_angle_type(self):
        """Test that rotate_image raises TypeError for invalid angle type."""
        image = Image.new('RGB', (100, 100), color='red')
        with pytest.raises(TypeError, match="Angle must be a numeric value"):
            rotate_image(image, "90")
    
    def test_rotate_image_zero_degrees(self):
        """Test that rotate_image returns a copy for 0-degree rotation."""
        image = Image.new('RGB', (100, 100), color='blue')
        rotated = rotate_image(image, 0)
        
        # Should return a different object (copy)
        assert rotated is not image
        
        # Should have same dimensions and content
        assert rotated.size == image.size
        assert np.array_equal(np.array(rotated), np.array(image))
        
        # Pixel-level verification
        rotated_array = np.array(rotated)
        original_array = np.array(image)
        assert np.array_equal(rotated_array, original_array), "Pixel values should be identical"
    
    def test_rotate_image_90_degrees(self):
        """Test 90-degree rotation."""
        image = Image.new('RGB', (100, 200), color='green')
        rotated = rotate_image(image, 90)
        
        # Dimensions should be swapped
        assert rotated.size == (200, 100)
    
    def test_rotate_image_180_degrees(self):
        """Test 180-degree rotation."""
        image = Image.new('RGB', (100, 100), color='yellow')
        rotated = rotate_image(image, 180)
        
        # Dimensions should remain the same
        assert rotated.size == (100, 100)
    
    def test_rotate_image_270_degrees(self):
        """Test 270-degree rotation."""
        image = Image.new('RGB', (100, 200), color='purple')
        rotated = rotate_image(image, 270)
        
        # Dimensions should be swapped
        assert rotated.size == (200, 100)
    
    def test_rotate_image_45_degrees(self):
        """Test 45-degree rotation."""
        image = Image.new('RGB', (100, 100), color='orange')
        rotated = rotate_image(image, 45)
        
        # For non-90-degree rotations, the bounding box expands
        # The new size should be larger than the original
        assert rotated.size[0] > 100
        assert rotated.size[1] > 100
    
    def test_rotate_image_negative_angle(self):
        """Test negative angle rotation."""
        image = Image.new('RGB', (100, 100), color='pink')
        rotated = rotate_image(image, -90)
        
        # -90 degrees should be equivalent to 270 degrees
        assert rotated.size == (100, 100)
    
    def test_rotate_image_large_angle(self):
        """Test angle larger than 360 degrees."""
        image = Image.new('RGB', (100, 100), color='cyan')
        rotated = rotate_image(image, 450)  # 450 = 360 + 90
        
        # Should be equivalent to 90-degree rotation
        assert rotated.size == (100, 100)
    
    def test_rotate_image_float_angle(self):
        """Test rotation with float angle."""
        image = Image.new('RGB', (100, 100), color='magenta')
        rotated = rotate_image(image, 45.5)
        
        # Should work with float angles
        assert rotated.size[0] > 100
        assert rotated.size[1] > 100
    
    def test_rotate_image_rgba(self):
        """Test rotation with RGBA image."""
        image = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        rotated = rotate_image(image, 90)
        
        # Should maintain RGBA mode
        assert rotated.mode == 'RGBA'
        assert rotated.size == (100, 100)
    
    def test_rotate_image_grayscale(self):
        """Test rotation with grayscale image."""
        image = Image.new('L', (100, 100), color=128)
        rotated = rotate_image(image, 180)
        
        # Should maintain grayscale mode
        assert rotated.mode == 'L'
        assert rotated.size == (100, 100)


class TestIsValidRotationAngle:
    """Test cases for is_valid_rotation_angle function."""
    
    def test_valid_angles(self):
        """Test valid rotation angles."""
        assert is_valid_rotation_angle(0) == True
        assert is_valid_rotation_angle(90) == True
        assert is_valid_rotation_angle(180) == True
        assert is_valid_rotation_angle(270) == True
        assert is_valid_rotation_angle(360) == True
        assert is_valid_rotation_angle(-90) == True
        assert is_valid_rotation_angle(45.5) == True
        assert is_valid_rotation_angle(0.0) == True
    
    def test_invalid_angles(self):
        """Test invalid rotation angles."""
        assert is_valid_rotation_angle("90") == False
        assert is_valid_rotation_angle(None) == False
        assert is_valid_rotation_angle([]) == False
        assert is_valid_rotation_angle({}) == False
        assert is_valid_rotation_angle(float('nan')) == False
        assert is_valid_rotation_angle(float('inf')) == False


class TestNormalizeRotationAngle:
    """Test cases for normalize_rotation_angle function."""
    
    def test_normalize_positive_angles(self):
        """Test normalization of positive angles."""
        assert normalize_rotation_angle(0) == 0.0
        assert normalize_rotation_angle(90) == 90.0
        assert normalize_rotation_angle(360) == 0.0
        assert normalize_rotation_angle(450) == 90.0
        assert normalize_rotation_angle(720) == 0.0
    
    def test_normalize_negative_angles(self):
        """Test normalization of negative angles."""
        assert normalize_rotation_angle(-90) == 270.0
        assert normalize_rotation_angle(-180) == 180.0
        assert normalize_rotation_angle(-360) == 0.0
        assert normalize_rotation_angle(-450) == 270.0
    
    def test_normalize_float_angles(self):
        """Test normalization of float angles."""
        assert normalize_rotation_angle(45.5) == 45.5
        assert normalize_rotation_angle(360.5) == 0.5
        assert normalize_rotation_angle(-45.5) == 314.5

    def test_normalize_edge_cases(self):
        """Test normalization edge cases with math.fmod."""
        # Test very large positive angles
        assert normalize_rotation_angle(720) == 0.0
        assert normalize_rotation_angle(1080) == 0.0
        assert normalize_rotation_angle(360 * 10 + 45) == 45.0
        
        # Test very large negative angles
        assert normalize_rotation_angle(-720) == 0.0
        assert normalize_rotation_angle(-1080) == 0.0
        assert normalize_rotation_angle(-360 * 10 - 45) == 315.0
        
        # Test angles that are exact multiples of 360
        assert normalize_rotation_angle(360.0) == 0.0
        assert normalize_rotation_angle(720.0) == 0.0
        assert normalize_rotation_angle(-360.0) == 0.0
        assert normalize_rotation_angle(-720.0) == 0.0
        
        # Test very small angles (use approximate comparison for floating-point)
        assert normalize_rotation_angle(0.1) == 0.1
        assert normalize_rotation_angle(-0.1) == 359.9
        assert normalize_rotation_angle(359.9) == 359.9
        # Use approximate comparison for floating-point precision issues
        result = normalize_rotation_angle(-359.9)
        assert abs(result - 0.1) < 1e-9, f"Expected 0.1, got {result}"
    
    def test_normalize_invalid_angles(self):
        """Test that invalid angles raise ValueError."""
        with pytest.raises(ValueError, match="Invalid rotation angle"):
            normalize_rotation_angle("90")
        
        with pytest.raises(ValueError, match="Invalid rotation angle"):
            normalize_rotation_angle(None)
        
        with pytest.raises(ValueError, match="Invalid rotation angle"):
            normalize_rotation_angle([])


class TestImageRotationEdgeCases:
    """Test edge cases for image rotation."""
    
    def test_rotate_very_small_image(self):
        """Test rotation of a very small image (1x1 pixel)."""
        image = Image.new('RGB', (1, 1), color='white')
        rotated = rotate_image(image, 90)
        
        # Should handle small images without error
        assert rotated.size == (1, 1)
    
    def test_rotate_very_large_image(self):
        """Test rotation of a large image."""
        image = Image.new('RGB', (10000, 10000), color='black')
        rotated = rotate_image(image, 180)
        
        # Should handle large images
        assert rotated.size == (10000, 10000)
    
    def test_rotate_image_with_alpha_transparency(self):
        """Test rotation of image with alpha transparency."""
        # Create an image with transparent background
        image = Image.new('RGBA', (100, 100), color=(255, 255, 255, 0))
        rotated = rotate_image(image, 90)
        
        # Should maintain transparency
        assert rotated.mode == 'RGBA'
        assert rotated.size == (100, 100)
    
    def test_rotate_image_multiple_times(self):
        """Test multiple sequential rotations."""
        # Create an image with distinct content for verification
        image = Image.new('RGB', (100, 200), color='red')
        draw = ImageDraw.Draw(image)
        draw.rectangle([(10, 10), (90, 190)], fill='blue')
        
        # Rotate 90 degrees twice (should be equivalent to 180 degrees)
        rotated1 = rotate_image(image, 90)
        rotated2 = rotate_image(rotated1, 90)
        
        assert rotated1.size == (200, 100)
        assert rotated2.size == (100, 200)
        
        # Content verification - check that the blue rectangle is still present
        rotated2_array = np.array(rotated2)
        # Find blue pixels (should be present in the rotated image)
        blue_pixels = np.all(rotated2_array == [0, 0, 255], axis=-1)
        assert np.any(blue_pixels), "Content should be preserved after multiple rotations"
    
    def test_rotate_image_360_degrees(self):
        """Test 360-degree rotation (should return to original orientation)."""
        image = Image.new('RGB', (100, 100), color='blue')
        rotated = rotate_image(image, 360)
        
        # Should be equivalent to 0-degree rotation
        assert rotated.size == (100, 100)
        assert np.array_equal(np.array(rotated), np.array(image))


if __name__ == "__main__":
    pytest.main([__file__])
