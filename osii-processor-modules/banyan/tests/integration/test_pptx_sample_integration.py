"""
Integration test for PPTX processing using the slides.pptx sample file.

This test module validates the complete PPTX processing workflow:
- Processing the actual slides.pptx file (not mocked)
- Validating output against expected files in tests/data/doc_outputs/pptx/
- Testing both text extraction and image handling
- Following existing fixture patterns from conftest.py

Generated using AI, reviewed by a human
"""

import os
import json
from pathlib import Path

import pytest


@pytest.fixture
def slides_pptx_file(test_data_dir):
    """Return path to the slides.pptx test file."""
    return test_data_dir / "docs" / "slides.pptx"


@pytest.fixture
def expected_pptx_output_dir(test_data_dir):
    """Return path to expected PPTX output directory."""
    return test_data_dir / "doc_outputs" / "pptx"


@pytest.mark.core
class TestPptxSampleIntegration:
    """Integration tests for PPTX processing using the slides.pptx sample file."""

    def test_pptx_processing_complete_workflow(self, slides_pptx_file, expected_pptx_output_dir, temp_output_dir, pptx_processor):
        """
        Test complete PPTX processing workflow using the slides.pptx sample file.
        
        This integration test demonstrates:
        - Processing an actual PPTX file (not mocked)
        - Validating text extraction from slides
        - Validating image extraction and saving
        - Comparing output against expected results
        - Using real file operations to ensure production compatibility
        
        Uses the slides.pptx file and validates against expected outputs.
        """
        # Verify the test file exists
        assert slides_pptx_file.exists(), f"Test file not found: {slides_pptx_file}"
        
        # Verify expected output files exist
        expected_md_file = expected_pptx_output_dir / "slides.md"
        expected_meta_file = expected_pptx_output_dir / "slides_meta.json"
        
        assert expected_md_file.exists(), f"Expected markdown file not found: {expected_md_file}"
        assert expected_meta_file.exists(), f"Expected metadata file not found: {expected_meta_file}"
        
        # Process the PPTX file
        output = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify output structure
        assert output is not None, "Output should not be None"
        assert hasattr(output, 'text'), "Output should have text attribute"
        assert hasattr(output, 'images'), "Output should have images attribute"
        assert hasattr(output, 'metadata'), "Output should have metadata attribute"
        
        # Verify we have slide data
        assert len(output.text) > 0, "Should extract text from at least one slide"
        
        # Save the output to temporary directory
        output_dir = temp_output_dir
        base_name = "slides"
        output.save_output(output_dir, base_name)
        
        # Verify expected files were created
        expected_output_files = [
            f"{base_name}.md",
            f"{base_name}_meta.json"
        ]
        
        for expected_file in expected_output_files:
            file_path = output_dir / expected_file
            assert file_path.exists(), f"Expected output file not found: {expected_file}"
        
        # Read and validate the markdown output
        md_file = output_dir / f"{base_name}.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        # Read expected markdown content
        with open(expected_md_file, 'r') as f:
            expected_md_content = f.read()
        
        # Validate markdown structure - should have slide headers
        assert "# Slide" in md_content, "Markdown should contain slide headers"
        
        # Validate that expected content is present
        expected_content_checks = [
            "This is a title",
            "This is a subtitle",
            "This is another slide",
            "Here is some sample text"
        ]
        
        for expected_text in expected_content_checks:
            assert expected_text in md_content, f"Expected text not found in output: {expected_text}"
        
        # Validate metadata file
        meta_file = output_dir / f"{base_name}_meta.json"
        with open(meta_file, 'r') as f:
            meta_content = f.read()
        
        # Metadata should be valid JSON
        metadata = json.loads(meta_content)
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        
        # Compare with expected metadata
        with open(expected_meta_file, 'r') as f:
            expected_metadata = json.load(f)
        
        assert metadata == expected_metadata, "Metadata should match expected output"
        
        # Verify slide count matches expected
        expected_slide_count = expected_md_content.count("# Slide")
        actual_slide_count = md_content.count("# Slide")
        
        assert actual_slide_count == expected_slide_count, \
            f"Slide count mismatch: expected {expected_slide_count}, got {actual_slide_count}"

    def test_pptx_text_extraction_accuracy(self, slides_pptx_file, pptx_processor):
        """
        Test the accuracy of text extraction from PPTX slides.
        
        This test validates that:
        - Text is correctly extracted from text frames
        - Slide structure is preserved
        - Text content matches expected values
        """
        # Process the PPTX file
        output = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify we extracted text from slides
        assert len(output.text) >= 2, "Should extract text from multiple slides"
        
        # Validate specific text content from known slides
        slide_texts = "\n".join(output.text)
        
        # Check for expected content from slide 0
        assert "This is a title" in slide_texts, "Should extract title from slide 0"
        assert "This is a subtitle" in slide_texts, "Should extract subtitle from slide 0"
        
        # Check for expected content from slide 1
        assert "This is another slide" in slide_texts, "Should extract title from slide 1"
        assert "Here is some sample text" in slide_texts, "Should extract text from slide 1"
        
        # Verify text is properly structured with newlines
        for slide_text in output.text:
            assert isinstance(slide_text, str), "Each slide text should be a string"
            assert len(slide_text) > 0, "Each slide should have some text content"

    def test_pptx_image_extraction(self, slides_pptx_file, pptx_processor, temp_output_dir):
        """
        Test image extraction from PPTX slides.
        
        This test validates that:
        - Images are correctly extracted from slides
        - Images are saved in the correct format
        - Image files are valid and can be opened
        """
        # Process the PPTX file
        output = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify images structure
        assert hasattr(output, 'images'), "Output should have images attribute"
        assert isinstance(output.images, list), "Images should be a list"
        
        # Save output to verify image files are created
        output_dir = temp_output_dir
        base_name = "slides_images"
        output.save_output(output_dir, base_name)
        
        # Check if any image files were created
        image_files = list(output_dir.glob("Slide_*.png"))
        
        # Note: The slides.pptx file may or may not contain images
        # If there are images, verify they are valid PNG files
        if image_files:
            from PIL import Image
            
            for image_file in image_files:
                # Verify the file is a valid image
                with Image.open(image_file) as img:
                    assert img.format == 'PNG', f"Image should be PNG format: {image_file}"
                    assert img.size[0] > 0 and img.size[1] > 0, f"Image should have valid dimensions: {image_file}"
        else:
            # If no images in the PPTX, verify that images list is empty or contains empty lists
            for slide_images in output.images:
                assert isinstance(slide_images, list), "Each slide should have an images list"

    def test_pptx_output_consistency(self, slides_pptx_file, pptx_processor):
        """
        Test that PPTX processing produces consistent results across multiple runs.
        
        This test validates that:
        - Processing the same file multiple times produces identical results
        - Output is deterministic and reliable
        """
        # Process the file multiple times
        output1 = pptx_processor.process_document(str(slides_pptx_file))
        output2 = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify text extraction is consistent
        assert output1.text == output2.text, "Text extraction should be consistent across runs"
        
        # Verify metadata is consistent
        assert output1.metadata == output2.metadata, "Metadata should be consistent across runs"
        
        # Verify images structure is consistent
        assert len(output1.images) == len(output2.images), "Image structure should be consistent"

    def test_pptx_error_handling(self, pptx_processor):
        """
        Test error handling for PPTX processing.
        
        This test validates that:
        - Invalid file paths are handled gracefully
        - Missing files produce appropriate errors
        """
        # Test with non-existent file
        with pytest.raises(Exception):  # Should raise some exception for invalid file
            pptx_processor.process_document("/non/existent/file.pptx")

    def test_pptx_metadata_structure(self, slides_pptx_file, pptx_processor):
        """
        Test the structure and content of PPTX metadata.
        
        This test validates that:
        - Metadata is properly structured
        - Metadata can be serialized to JSON
        - Metadata contains expected fields
        """
        # Process the PPTX file
        output = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify metadata structure
        assert isinstance(output.metadata, dict), "Metadata should be a dictionary"
        
        # Verify metadata can be serialized to JSON
        json_str = json.dumps(output.metadata)
        parsed_metadata = json.loads(json_str)
        
        assert parsed_metadata == output.metadata, "Metadata should be JSON-serializable"

    def test_pptx_slide_structure(self, slides_pptx_file, pptx_processor):
        """
        Test the structure of extracted slide data.
        
        This test validates that:
        - Each slide has associated text and images
        - Slide data is properly organized
        - Text and images are aligned by slide index
        """
        # Process the PPTX file
        output = pptx_processor.process_document(str(slides_pptx_file))
        
        # Verify we have consistent slide data
        num_slides = len(output.text)
        assert num_slides > 0, "Should have at least one slide"
        
        # Verify images list matches text list structure
        assert len(output.images) == num_slides, \
            f"Images list should match text list: {len(output.images)} vs {num_slides}"
        
        # Verify each slide has appropriate data
        for slide_idx in range(num_slides):
            slide_text = output.text[slide_idx]
            slide_images = output.images[slide_idx]
            
            assert isinstance(slide_text, str), f"Slide {slide_idx} text should be a string"
            assert isinstance(slide_images, list), f"Slide {slide_idx} images should be a list"
            assert len(slide_text) > 0, f"Slide {slide_idx} should have some text content"
