"""
Unit tests for NemoparseProcessor class.

These tests verify the functionality of the NemoparseProcessor class
using mocking for external dependencies like the Nemotron OCR API.

Dependency Requirements: nemotronparse dependencies (openai) for full testing

Test Organization:
- Initialization tests: Test constructor and setup
- Core functionality tests: Test main processing methods
- Error handling tests: Test robust error handling
- Input validation tests: Test input parameter validation
- Edge case tests: Test boundary conditions and unusual scenarios
- Integration tests: Test multi-component interactions
"""

import os
import io
import base64
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

import pytest

NemoparseProcessor = pytest.importorskip("banyan_extract.processor.nemoparse_processor").NemoparseProcessor
NemoparseData = pytest.importorskip("banyan_extract.output.nemoparse_output").NemoparseData


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorInitialization:
    """Tests for NemoparseProcessor initialization."""

    def test_initialization_with_default_parameters(self):
        """Test that NemoparseProcessor initializes with default parameters."""
        processor = NemoparseProcessor()
        
        assert processor.nemotron_ocr is not None
        assert processor.nemotron_ocr.model_url == ""
        assert processor.nemotron_ocr.model == "nvidia/nemoretriever-parse"
        assert processor.sort_by_position == True

    def test_initialization_with_custom_parameters(self):
        """Test that NemoparseProcessor initializes with custom parameters."""
        custom_endpoint = "http://custom-endpoint:8000/v1"
        custom_model = "custom/nemoparse-model"
        custom_sort = False
        
        processor = NemoparseProcessor(
            endpoint_url=custom_endpoint,
            model_name=custom_model,
            sort_by_position=custom_sort
        )
        
        assert processor.nemotron_ocr.model_url == custom_endpoint
        assert processor.nemotron_ocr.model == custom_model
        assert processor.sort_by_position == custom_sort


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorSorting:
    """Tests for the sort_elements_by_position method."""

    def test_sort_elements_by_position_functionality(self):
        """Test that elements are sorted correctly by spatial position."""
        processor = NemoparseProcessor()
        
        # Sample bbox data with different positions
        bbox_data = [
            {
                'type': 'Text',
                'bbox': {'xmin': 0.5, 'ymin': 0.5, 'xmax': 0.8, 'ymax': 0.6},
                'text': 'Bottom text'
            },
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'Top header'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.2, 'ymin': 0.3, 'xmax': 0.7, 'ymax': 0.4},
                'text': 'Middle text'
            }
        ]
        
        width, height = 1000, 1000
        sorted_elements = processor.sort_elements_by_position(bbox_data, width, height)
        
        # Verify sorting order (should be: header, middle text, bottom text)
        assert sorted_elements[0]['text'] == 'Top header'
        assert sorted_elements[1]['text'] == 'Middle text'
        assert sorted_elements[2]['text'] == 'Bottom text'
        
        # Verify type priority (headers should come before text at same position)
        same_position_elements = [
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                'text': 'Text element'
            },
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                'text': 'Header element'
            }
        ]
        
        sorted_same_pos = processor.sort_elements_by_position(same_position_elements, width, height)
        assert sorted_same_pos[0]['type'] == 'Section-header'
        assert sorted_same_pos[1]['type'] == 'Text'


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorImageProcessing:
    """Tests for image processing methods."""

    def test_encode_image_success(self):
        """Test successful image encoding."""
        processor = NemoparseProcessor()
        
        # Create a test image
        test_image = b'sample_image_data'
        
        # Use real base64 encoding instead of mocking
        # base64 encoding is a simple, reliable utility function
        result = processor._encode_image(test_image)
        
        # Verify the result using real base64 encoding
        expected_result = base64.b64encode(test_image).decode('utf-8')
        assert result == expected_result

    def test_encode_image_failure(self):
        """Test image encoding failure handling."""
        processor = NemoparseProcessor()
        
        # Test with empty image data (should raise ValueError and return None)
        empty_image = b''
        result = processor._encode_image(empty_image)
        assert result is None
        
        # Test with None image data (should raise ValueError and return None)
        result = processor._encode_image(None)
        assert result is None


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorErrorHandling:
    """Error handling tests for NemoparseProcessor."""

    def test_batch_processing_error_handling(self):
        """Test handling of errors during batch processing."""
        processor = NemoparseProcessor()
        
        # Create mock images
        mock_image1 = Image.new('RGB', (100, 100), color='white')
        mock_image2 = Image.new('RGB', (100, 100), color='lightgray')
        
        # Convert images to bytes
        img_byte_arr1 = io.BytesIO()
        mock_image1.save(img_byte_arr1, format='PNG')
        image_bytes1 = img_byte_arr1.getvalue()
        
        img_byte_arr2 = io.BytesIO()
        mock_image2.save(img_byte_arr2, format='PNG')
        image_bytes2 = img_byte_arr2.getvalue()
        
        def mock_ocr_response(base64_image, **kwargs):
            # Check if the base64 image contains doc1 or doc2 identifier
            # Since we can't easily inspect base64 content, we'll use a counter
            if not hasattr(mock_ocr_response, 'call_count'):
                mock_ocr_response.call_count = 0
            
            mock_ocr_response.call_count += 1
            
            if mock_ocr_response.call_count == 1:  # First call (doc1)
                return [
                    {
                        'type': 'Text',
                        'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                        'text': 'Document 1 text'
                    }
                ]
            else:  # Second call (doc2)
                raise Exception("API error for document 2")
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_response)
        
        # Mock the get_pages method
        def mock_get_pages(filepath):
            if 'doc1' in filepath:
                return [image_bytes1]
            elif 'doc2' in filepath:
                return [image_bytes2]
            return []
        
        processor.get_pages = Mock(side_effect=mock_get_pages)
        
        # Process batch documents - should handle errors gracefully and continue
        filepaths = ['doc1.pdf', 'doc2.pdf']
        
        # Should not raise exception - should handle errors gracefully
        results = processor.process_batch_documents(filepaths, use_checkpointing=False)
        
        # Should return results for successful documents only
        assert len(results) == 1  # Only doc1 should be processed successfully
        assert results[0] is not None
        assert 'Document 1 text' in results[0].text[0][0]


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorEdgeCases:
    """Edge case tests for NemoparseProcessor."""

    def test_handle_empty_document(self):
        """Test handling of empty document (no pages)."""
        processor = NemoparseProcessor()
        
        # Mock get_pages to return empty list
        processor.get_pages = Mock(return_value=[])
        
        # Process the document
        result = processor.process_document("empty.pdf")
        
        # Verify the result (should have empty data but not crash)
        assert result is not None
        assert len(result.text) == 0
        assert len(result.bboxdata) == 0

    def test_process_document_with_sorting_disabled(self):
        """Test document processing with sorting disabled."""
        processor = NemoparseProcessor(sort_by_position=False)
        
        # Create a real test image
        real_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the OCR API response with unsorted data (KEEP THIS - external dependency)
        mock_bbox_data = [
            {
                'type': 'Text',
                'bbox': {'xmin': 0.5, 'ymin': 0.5, 'xmax': 0.8, 'ymax': 0.6},
                'text': 'Bottom text'
            },
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'Top header'
            }
        ]
        
        # Mock the nemotron_ocr.get_detailed_ocr_results method
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
        
        # Use more realistic get_pages implementation
        def real_get_pages(filepath):
            return [image_bytes]
        
        processor.get_pages = real_get_pages
        
        # Process the document
        result = processor.process_document("test.pdf")
        
        # Verify the result (should preserve original order when sorting is disabled)
        assert result is not None
        assert len(result.text) == 1
        
        # When sorting is disabled, the order should match the original bbox_data
        text_content = result.text[0]
        assert text_content[0] == 'Bottom text'  # First in original data
        assert text_content[1] == '# Top header'   # Second in original data (with # prefix)

    def test_process_document_with_special_characters(self):
        """Test document processing with special characters in text."""
        processor = NemoparseProcessor()
        
        # Create a real test image
        real_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the OCR API response with special characters (KEEP THIS - external dependency)
        mock_bbox_data = [
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.8, 'ymax': 0.2},
                'text': 'Text with special chars: (c)(R)(TM)&<>'
            }
        ]
        
        # Mock the nemotron_ocr.get_detailed_ocr_results method
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
        
        # Use more realistic get_pages implementation
        def real_get_pages(filepath):
            return [image_bytes]
        
        processor.get_pages = real_get_pages
        
        # Process the document
        result = processor.process_document("test.pdf")
        
        # Verify the result preserves special characters
        assert result is not None
        assert len(result.text) == 1
        assert 'Text with special chars: (c)(R)(TM)&<>' in result.text[0]


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorInputValidation:
    """Input validation tests for NemoparseProcessor."""

    def test_process_document_with_invalid_filepath(self):
        """Test handling of invalid file paths."""
        processor = NemoparseProcessor()
        
        # Test with None filepath
        with pytest.raises(Exception):
            processor.process_document(None)
        
        # Test with empty string filepath
        with pytest.raises(Exception):
            processor.process_document("")
        
        # Test with non-existent file
        with pytest.raises(Exception):
            processor.process_document("/non/existent/file.pdf")

    def test_process_page_with_invalid_image(self):
        """Test handling of invalid image data."""
        processor = NemoparseProcessor()
        
         # Test with None image data - should raise exception
        with pytest.raises(Exception):
            processor.process_document(None)
        
        # Test with empty bytes - should raise exception
        with pytest.raises(Exception):
            processor.process_document(b"")
        
        # Test with invalid image bytes - should raise exception
        with pytest.raises(Exception):
            processor.process_document(b"invalid_image_data")

    def test_process_batch_with_empty_list(self):
        """Test handling of empty file list in batch processing."""
        processor = NemoparseProcessor()
        
        # Test with empty list
        results = processor.process_batch_documents([], use_checkpointing=False)
        assert len(results) == 0
        
        # Test with None - should raise exception
        with pytest.raises(TypeError):
            processor.process_batch_documents(None, use_checkpointing=False)

    def test_process_batch_with_invalid_filepaths(self):
        """Test handling of invalid file paths in batch processing."""
        processor = NemoparseProcessor()
        
        # Test with list containing None and invalid paths
        filepaths = ["", "/non/existent/file.pdf"]
        
        # Mock get_pages to handle the invalid paths gracefully
        def mock_get_pages(filepath):
            if filepath is None or filepath == "" or not os.path.exists(filepath):
                return []
            return [b"mock_image_data"]
        
        processor.get_pages = Mock(side_effect=mock_get_pages)
        
        # Process batch - should handle invalid paths gracefully
        results = processor.process_batch_documents(filepaths, use_checkpointing=False)
        
        # Should return results for all filepaths (even if empty)
        assert len(results) == len(filepaths)
        assert all(result is not None for result in results)


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorFileHandling:
    """Tests for file handling methods."""

    def test_get_pages_with_png_file(self, tmp_path):
        """Test get_pages method with PNG file."""
        processor = NemoparseProcessor()
        
        # Create a temporary PNG file using tmp_path
        png_file = tmp_path / "test_image.png"
        
        # Create a simple PNG image
        img = Image.new('RGB', (100, 100), color='white')
        img.save(png_file, format='PNG')
        
        # Test get_pages with PNG file
        pages = processor.get_pages(str(png_file))
        
        # Verify we get one page
        assert len(pages) == 1
        assert isinstance(pages[0], bytes)

    def test_get_pages_with_unsupported_file(self, tmp_path):
        """Test get_pages method with unsupported file type."""
        processor = NemoparseProcessor()
        
        # Create a temporary file with unsupported extension using tmp_path
        unsupported_file = tmp_path / "test_file.unsupported"
        unsupported_file.write_bytes(b'test content')
        
        # Test get_pages with unsupported file - should raise exception
        with pytest.raises(Exception) as exc_info:
            processor.get_pages(str(unsupported_file))
        
        assert "Unsupported filetype" in str(exc_info.value)


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorIntegration:
    """Integration tests for NemoparseProcessor."""

    def test_process_batch_documents(self):
        """Test batch document processing."""
        processor = NemoparseProcessor()
        
        # Create mock images
        mock_image1 = Image.new('RGB', (100, 100), color='white')
        mock_image2 = Image.new('RGB', (100, 100), color='lightgray')
        
        # Convert images to bytes
        img_byte_arr1 = io.BytesIO()
        mock_image1.save(img_byte_arr1, format='PNG')
        image_bytes1 = img_byte_arr1.getvalue()
        
        img_byte_arr2 = io.BytesIO()
        mock_image2.save(img_byte_arr2, format='PNG')
        image_bytes2 = img_byte_arr2.getvalue()
        
        # Mock the OCR API response
        mock_bbox_data = [
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                'text': 'Document 1 text'
            }
        ]
        
        # Mock the nemotron_ocr.get_detailed_ocr_results method
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
        
        # Mock the get_pages method
        def mock_get_pages(filepath):
            if 'doc1' in filepath:
                return [image_bytes1]
            elif 'doc2' in filepath:
                return [image_bytes2]
            return []
        
        processor.get_pages = Mock(side_effect=mock_get_pages)
        
        # Process batch documents
        filepaths = ['doc1.pdf', 'doc2.pdf']
        results = processor.process_batch_documents(filepaths, use_checkpointing=False)
        
        # Verify we got results for both documents
        assert len(results) == 2
        assert all(result is not None for result in results)

    def test_process_document_with_multiple_pages(self):
        """Test document processing with multiple pages."""
        processor = NemoparseProcessor()
        
        # Create real test images for multiple pages
        # This replaces the mock images with real image data
        real_images = []
        colors = ['white', 'lightgray', 'gray']
        for i in range(3):
            img = Image.new('RGB', (100, 100), color=colors[i])
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            real_images.append(img_byte_arr.getvalue())
        
        # Mock the OCR API response (KEEP THIS - external dependency)
        def mock_ocr_response(base64_image, **kwargs):
            page_num = len(mock_ocr_responses) + 1
            mock_ocr_responses.append(page_num)
            return [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': f'Page {page_num} text'
                }
            ]
        
        mock_ocr_responses = []
        
        # Mock the nemotron_ocr.get_detailed_ocr_results method
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_response)
        
        # Use real get_pages method instead of mocking
        # We'll override get_pages to use our real test images
        # This is still a form of mocking, but it's more realistic than returning pre-made byte arrays
        def real_get_pages(filepath):
            # Return our real test images instead of processing actual files
            # This approach allows us to test the processing logic with real image data
            return real_images
        
        processor.get_pages = real_get_pages
        
        # Process the document
        result = processor.process_document("multi_page.pdf")
        
        # Verify we got results for all pages
        assert result is not None
        assert len(result.text) == 3  # One entry per page
        
        # Verify each page's text is present
        for i, page_text in enumerate(result.text):
            assert f'Page {i+1} text' in page_text[0]


@pytest.mark.requires_nemotronparse
class TestNemoparseProcessorRotationDetection:
    """Tests for rotation detection functionality in NemoparseProcessor."""

    def test_process_image_with_auto_detect_rotation_success(self):
        """Test successful auto rotation detection in _process_image."""
        processor = NemoparseProcessor()
        
        # Create a mock image
        mock_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        mock_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the rotation detection to return a 90-degree rotation
        with patch('banyan_extract.processor.nemoparse_processor.detect_rotation_angle_with_fallback') as mock_detect:
            mock_detect.return_value = 90.0
            
            # Mock the OCR API response
            mock_bbox_data = [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': 'Rotated text'
                }
            ]
            
            # Mock the nemotron_ocr.get_detailed_ocr_results method
            processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
            
            # Process the image with auto-detection enabled
            result = processor._process_image(
                image_bytes, 
                auto_detect_rotation=True,
                rotation_confidence_threshold=0.7
            )
            
            # Verify rotation detection was called
            mock_detect.assert_called_once()
            
            # Verify the result
            assert result is not None
            assert isinstance(result, NemoparseData)
            assert len(result.text) == 1
            assert 'Rotated text' in result.text[0]

    def test_process_image_with_auto_detect_rotation_failure(self):
        """Test graceful handling of rotation detection failure."""
        processor = NemoparseProcessor()
        
        # Create a mock image
        mock_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        mock_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the rotation detection to raise an exception
        with patch('banyan_extract.processor.nemoparse_processor.detect_rotation_angle_with_fallback') as mock_detect:
            mock_detect.side_effect = Exception("Tesseract not available")
            
            # Mock the OCR API response
            mock_bbox_data = [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': 'Non-rotated text'
                }
            ]
            
            # Mock the nemotron_ocr.get_detailed_ocr_results method
            processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
            
            # Process the image with auto-detection enabled - should not crash
            result = processor._process_image(
                image_bytes, 
                auto_detect_rotation=True,
                rotation_confidence_threshold=0.7
            )
            
            # Verify rotation detection was called
            mock_detect.assert_called_once()
            
            # Verify the result - should still process the image without rotation
            assert result is not None
            assert isinstance(result, NemoparseData)
            assert len(result.text) == 1
            assert 'Non-rotated text' in result.text[0]

    def test_process_image_manual_rotation_takes_precedence(self):
        """Test that manual rotation takes precedence over auto-detection."""
        processor = NemoparseProcessor()
        
        # Create a mock image
        mock_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        mock_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the rotation detection to return a rotation angle
        with patch('banyan_extract.processor.nemoparse_processor.detect_rotation_angle_with_fallback') as mock_detect:
            mock_detect.return_value = 90.0
            
            # Mock the OCR API response
            mock_bbox_data = [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': 'Manually rotated text'
                }
            ]
            
            # Mock the nemotron_ocr.get_detailed_ocr_results method
            processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
            
            # Process the image with both manual rotation and auto-detection enabled
            result = processor._process_image(
                image_bytes, 
                rotation_angle=180,
                auto_detect_rotation=True,
                rotation_confidence_threshold=0.7
            )
            
            # Verify rotation detection was called (but manual rotation should take precedence)
            mock_detect.assert_called_once()
            
            # Verify the result
            assert result is not None
            assert isinstance(result, NemoparseData)
            assert len(result.text) == 1
            assert 'Manually rotated text' in result.text[0]

    def test_process_document_with_auto_detect_rotation(self):
        """Test document processing with auto rotation detection enabled."""
        processor = NemoparseProcessor()
        
        # Create a real test image
        real_image = Image.new('RGB', (100, 100), color='white')
        
        # Convert image to bytes
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        image_bytes = img_byte_arr.getvalue()
        
        # Mock the rotation detection (KEEP THIS - complex external dependency)
        with patch('banyan_extract.processor.nemoparse_processor.detect_rotation_angle_with_fallback') as mock_detect:
            mock_detect.return_value = 0.0  # No rotation needed
            
            # Mock the OCR API response (KEEP THIS - external dependency)
            mock_bbox_data = [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': 'Auto-detected document text'
                }
            ]
            
            # Mock the nemotron_ocr.get_detailed_ocr_results method
            processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
            
            # Use more realistic get_pages implementation
            def real_get_pages(filepath):
                return [image_bytes]
            
            processor.get_pages = real_get_pages
            
            # Process the document with auto-detection enabled
            result = processor.process_document(
                "test.pdf",
                auto_detect_rotation=True,
                rotation_confidence_threshold=0.7
            )
            
            # Verify rotation detection was called
            mock_detect.assert_called_once()
            
            # Verify the result
            assert result is not None
            assert len(result.text) == 1
            assert 'Auto-detected document text' in result.text[0]

    def test_process_batch_with_auto_detect_rotation(self):
        """Test batch processing with auto rotation detection enabled."""
        processor = NemoparseProcessor()
        
        # Create mock images
        mock_image1 = Image.new('RGB', (100, 100), color='white')
        mock_image2 = Image.new('RGB', (100, 100), color='lightgray')
        
        # Convert images to bytes
        img_byte_arr1 = io.BytesIO()
        mock_image1.save(img_byte_arr1, format='PNG')
        image_bytes1 = img_byte_arr1.getvalue()
        
        img_byte_arr2 = io.BytesIO()
        mock_image2.save(img_byte_arr2, format='PNG')
        image_bytes2 = img_byte_arr2.getvalue()
        
        # Mock the rotation detection
        with patch('banyan_extract.processor.nemoparse_processor.detect_rotation_angle_with_fallback') as mock_detect:
            mock_detect.return_value = 0.0  # No rotation needed
            
            # Mock the OCR API response
            mock_bbox_data = [
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                    'text': 'Batch document text'
                }
            ]
            
            # Mock the nemotron_ocr.get_detailed_ocr_results method
            processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
            
            # Mock the get_pages method
            def mock_get_pages(filepath):
                if 'doc1' in filepath:
                    return [image_bytes1]
                elif 'doc2' in filepath:
                    return [image_bytes2]
                return []
            
            processor.get_pages = Mock(side_effect=mock_get_pages)
            
            # Process batch documents with auto-detection enabled
            filepaths = ['doc1.pdf', 'doc2.pdf']
            results = processor.process_batch_documents(
                filepaths, 
                use_checkpointing=False,
                auto_detect_rotation=True,
                rotation_confidence_threshold=0.7
            )
            
            # Verify rotation detection was called for each document
            assert mock_detect.call_count == 2
            
            # Verify the results
            assert len(results) == 2
            assert all(result is not None for result in results)
            assert all('Batch document text' in result.text[0][0] for result in results)


if __name__ == "__main__":
    pytest.main([__file__])
