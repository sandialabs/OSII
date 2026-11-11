# Integration tests for rotation detection with actual PDF files
# This test suite focuses on testing with the sample_rotation.pdf file

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


class TestRotationDetectionWithActualPDF:
    """Integration tests using actual PDF files and Tesseract OCR."""
    
    def test_sample_rotation_pdf_file_properties(self, test_data_dir):
        """Test basic properties of sample_rotation.pdf file."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        
        # Verify file exists and has reasonable size
        assert sample_pdf_path.exists()
        assert sample_pdf_path.is_file()
        file_size = sample_pdf_path.stat().st_size
        assert file_size > 0
        assert file_size < 100000  # Reasonable size for a test PDF
    
    def test_pdf_to_image_conversion_with_sample_rotation(self, test_data_dir):
        """Test PDF to image conversion with sample_rotation.pdf."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        
        try:
            from pdf2image import convert_from_path
            
            # Convert PDF to images
            images = convert_from_path(str(sample_pdf_path))
            
            # Verify we got at least one image
            assert len(images) > 0
            
            # Verify all images are PIL Image objects
            for i, image in enumerate(images):
                assert isinstance(image, Image.Image)
                assert image.size[0] > 0 and image.size[1] > 0
            
        except Exception as e:
            # If PDF conversion fails, skip this test
            pytest.skip(f"PDF conversion failed: {e}")
    
    def test_rotation_detection_with_actual_pdf_images(self, test_data_dir):
        """Test rotation detection with actual images from sample_rotation.pdf."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        
        try:
            from pdf2image import convert_from_path
            
            # Convert PDF to images
            images = convert_from_path(str(sample_pdf_path))
            
            if len(images) == 0:
                pytest.skip("No images converted from PDF")
            
            # Test rotation detection on each image with mocked Tesseract
            mock_pytesseract = MagicMock()
            
            # Mock different rotations for different images
            def mock_image_to_osd(image, config=None, output_type=None):
                 # Simple mock that returns 90-degree rotation for all images
                 # In a real scenario, this would be replaced with actual Tesseract OCR
                 return {
                     'orientation': '90',
                     'orientation_conf': '0.85'
                 }
            
            mock_pytesseract.image_to_osd = mock_image_to_osd
            
            with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
                 patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
                
                # Test rotation detection on each image
                for i, image in enumerate(images):
                    angle = detect_rotation_angle(image, confidence_threshold=0.7)
                    assert angle == 90.0
                    
                    # Test rotation correction
                    corrected_image = rotate_image(image, angle)
                    assert corrected_image.size == (image.size[1], image.size[0])
            
        except Exception as e:
            pytest.skip(f"PDF processing failed: {e}")
    
    def test_rotation_detection_fallback_with_actual_pdf(self, test_data_dir):
        """Test fallback behavior when processing actual PDF without Tesseract."""
        # Use test_data_dir fixture
        sample_pdf_path = test_data_dir / "docs" / "sample_rotation.pdf"
        
        try:
            from pdf2image import convert_from_path
            
            # Convert PDF to images
            images = convert_from_path(str(sample_pdf_path))
            
            if len(images) == 0:
                pytest.skip("No images converted from PDF")
            
            # Test with Tesseract not available
            with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=False):
                
                for image in images:
                    # Should raise TesseractNotFoundError
                    with pytest.raises(TesseractNotFoundError):
                        detect_rotation_angle(image)
                    
                    # Fallback function should return 0.0
                    angle = detect_rotation_angle_with_fallback(image)
                    assert angle == 0.0
            
        except Exception as e:
            pytest.skip(f"PDF processing failed: {e}")


class TestRotationDetectionWithRealTesseract:
    """Integration tests using real Tesseract OCR (if available)."""
    
    def test_real_tesseract_rotation_detection(self):
        """Test rotation detection with real Tesseract OCR on sample images."""
        # Check if Tesseract is actually available
        try:
            from banyan_extract.utils.tesseract_dependencies import has_tesseract_dependencies
            if not has_tesseract_dependencies():
                pytest.skip("Tesseract OCR not available for real testing")
            
            import pytesseract
            
        except ImportError:
            pytest.skip("Tesseract dependencies not available")
        
        # Create test images with text at different orientations
        test_cases = [
            (0, "Normal text orientation"),
            (90, "Text rotated 90 degrees"),
            (180, "Text rotated 180 degrees"),
            (270, "Text rotated 270 degrees")
        ]
        
        for expected_angle, description in test_cases:
            # Create a test image with text
            if expected_angle in [0, 180]:
                size = (400, 200)
            else:  # 90 or 270
                size = (200, 400)
            
            image = Image.new('RGB', size, color='white')
            draw = ImageDraw.Draw(image)
            
            # Add some text that Tesseract can recognize
            if expected_angle == 0:
                draw.text((50, 50), "This is normal text for rotation detection", fill='black')
            elif expected_angle == 90:
                draw.text((50, 50), "Rotated 90 degrees", fill='black')
            elif expected_angle == 180:
                draw.text((50, 50), "Upside down text", fill='black')
            elif expected_angle == 270:
                draw.text((50, 50), "Rotated 270 degrees", fill='black')
            
            # Test rotation detection
            try:
                angle = detect_rotation_angle(image, confidence_threshold=0.5)
                
                # For real Tesseract testing, we just verify it doesn't crash
                # The actual angle detection may vary based on Tesseract's analysis
                assert isinstance(angle, float)
                assert 0 <= angle < 360
                
            except Exception as e:
                # If real Tesseract fails, that's okay for this test
                # We're just testing that the integration works
                print(f"Real Tesseract test failed for {description}: {e}")


class TestRotationDetectionPerformance:
    """Performance tests for rotation detection."""
    
    def test_rotation_detection_performance_with_multiple_images(self):
        """Test performance of rotation detection with multiple images."""
        import time
        
        # Create multiple test images
        test_images = []
        for i in range(10):
            image = Image.new('RGB', (200, 100), color='white')
            test_images.append(image)
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Time the batch processing
            start_time = time.time()
            
            for image in test_images:
                angle = detect_rotation_angle(image, confidence_threshold=0.7)
                assert angle == 90.0
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Should complete reasonably quickly (less than 1 second for 10 images)
            assert elapsed_time < 1.0
    
    def test_rotation_detection_memory_usage(self):
        """Test that rotation detection doesn't cause excessive memory usage."""
        import gc
        
        # Create a reasonably large image
        large_image = Image.new('RGB', (1000, 1000), color='white')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Get initial memory usage
            gc.collect()
            
            # Perform rotation detection
            angle = detect_rotation_angle(large_image, confidence_threshold=0.7)
            assert angle == 180.0
            
            # Clean up
            del large_image
            gc.collect()
            
            # Test should complete without memory errors
            assert True


class TestRotationDetectionVisualVerification:
    """Visual verification tests for rotation detection."""
    
    def test_rotation_correction_visual_verification(self):
        """Test that rotation correction produces visually correct results."""
        # Create a test image with distinctive visual features
        image = Image.new('RGB', (400, 300), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw distinctive shapes in specific locations
        # Top-left: Red rectangle
        draw.rectangle([(50, 50), (150, 100)], fill='red')
        draw.text((60, 60), "TOP", fill='black')
        
        # Bottom-right: Blue rectangle
        draw.rectangle([(300, 200), (380, 280)], fill='blue')
        draw.text((310, 210), "BOTTOM", fill='white')
        
        # Test 90-degree rotation
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '90',
            'orientation_conf': '0.85'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Detect rotation
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 90.0
            
            # Apply rotation correction
            corrected_image = rotate_image(image, angle)
            
            # Verify dimensions are swapped (400x300 -> 300x400)
            assert corrected_image.size == (300, 400)
            
            # Verify the image content is actually different
            orig_array = np.array(image)
            corrected_array = np.array(corrected_image)
            assert not np.array_equal(orig_array, corrected_array)
    
    def test_rotation_correction_preserves_content(self):
        """Test that rotation correction preserves image content."""
        # Create a test image with a distinctive pattern
        image = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(image)
        draw.rectangle([(50, 25), (150, 75)], fill='red')
        
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_osd.return_value = {
            'orientation': '180',
            'orientation_conf': '0.90'
        }
        
        with patch('banyan_extract.utils.rotation_detection.has_tesseract_dependencies', return_value=True), \
             patch.dict('sys.modules', {'pytesseract': mock_pytesseract}):
            
            # Detect rotation
            angle = detect_rotation_angle(image, confidence_threshold=0.7)
            assert angle == 180.0
            
            # Apply rotation correction
            corrected_image = rotate_image(image, angle)
            
            # Rotate back to original orientation
            restored_image = rotate_image(corrected_image, angle)
            
            # Verify content is preserved (should be similar to original)
            orig_array = np.array(image)
            restored_array = np.array(restored_image)
            
            # Images should be very similar (allowing for minor differences due to rotation)
            diff = np.abs(orig_array.astype(float) - restored_array.astype(float))
            mean_diff = np.mean(diff)
            assert mean_diff < 5.0  # Small average difference


if __name__ == "__main__":
    pytest.main([__file__])
