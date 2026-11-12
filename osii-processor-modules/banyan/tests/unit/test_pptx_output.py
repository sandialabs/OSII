"""
Unit tests for PPTXOutput class.

These tests verify the functionality of the PPTXOutput class
for handling PowerPoint presentation output.
"""

import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

import pytest

from banyan_extract.output.pptx_output import PptxOutput


class TestPPTXOutputInitialization:
    """Tests for PPTXOutput initialization."""

    def test_initialization_with_valid_data(self):
        """Test initialization with valid text, images, and metadata."""
        # Create mock data
        text_data = ["Slide 1 content", "Slide 2 content"]
        images_data = [[Mock(), Mock()], [Mock()]]  # 2 slides, first with 2 images, second with 1
        metadata = {"title": "Test Presentation", "author": "Test Author"}
        
        # Create PPTXOutput instance
        output = PptxOutput(text_data, images_data, metadata)
        
        # Verify initialization
        assert output.text == text_data
        assert output.images == images_data
        assert output.metadata == metadata

    def test_initialization_with_empty_data(self):
        """Test initialization with empty data."""
        # Create PPTXOutput with empty data
        output = PptxOutput([], [], {})
        
        # Verify empty initialization
        assert output.text == []
        assert output.images == []
        assert output.metadata == {}

    def test_initialization_with_none_metadata(self):
        """Test initialization with None metadata."""
        # Create PPTXOutput with None metadata
        output = PptxOutput(["test"], [], None)
        
        # Verify None metadata is handled
        assert output.metadata is None


class TestPPTXOutputSaveOutput:
    """Tests for save_output method."""

    def test_save_output_success(self, tmp_path):
        """Test successful output saving."""
        # Create mock data
        text_data = ["Slide 1 content", "Slide 2 content"]
        
        # Create mock images
        mock_images = [
            [Image.new('RGB', (100, 100), color='white'), Image.new('RGB', (100, 100), color='lightgray')],
            [Image.new('RGB', (100, 100), color='gray')]
        ]
        
        metadata = {"title": "Test Presentation", "author": "Test Author"}
        
        # Create PPTXOutput instance
        output = PptxOutput(text_data, mock_images, metadata)
        
        # Save output
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "test_presentation")
        
        # Verify files were created
        assert (output_dir / "test_presentation.md").exists()
        assert (output_dir / "test_presentation_meta.json").exists()
        assert (output_dir / "Slide_0_image_0.png").exists()
        assert (output_dir / "Slide_0_image_1.png").exists()
        assert (output_dir / "Slide_1_image_0.png").exists()
        
        # Verify markdown content
        md_file = output_dir / "test_presentation.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        assert "# Slide 0" in md_content
        assert "# Slide 1" in md_content
        assert "Slide 1 content" in md_content
        assert "Slide 2 content" in md_content
        
        # Verify metadata JSON
        meta_file = output_dir / "test_presentation_meta.json"
        with open(meta_file, 'r') as f:
            meta_content = json.load(f)
        
        assert meta_content == metadata

    def test_save_output_with_empty_data(self, tmp_path):
        """Test saving output with empty data."""
        # Create PPTXOutput with empty data
        output = PptxOutput([], [], {})
        
        # Save output
        output_dir = tmp_path / "empty_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "empty_presentation")
        
        # Verify files were created (even with empty data)
        assert (output_dir / "empty_presentation.md").exists()
        assert (output_dir / "empty_presentation_meta.json").exists()
        
        # Verify empty content
        md_file = output_dir / "empty_presentation.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        assert md_content == ""  # Empty markdown file

    def test_save_output_with_no_images(self, tmp_path):
        """Test saving output with text but no images."""
        # Create PPTXOutput with text but no images
        text_data = ["Slide 1 content", "Slide 2 content"]
        metadata = {"title": "Text Only Presentation"}
        
        output = PptxOutput(text_data, [], metadata)
        
        # Save output
        output_dir = tmp_path / "text_only_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "text_only_presentation")
        
        # Verify files were created
        assert (output_dir / "text_only_presentation.md").exists()
        assert (output_dir / "text_only_presentation_meta.json").exists()
        
        # Verify no image files were created
        image_files = list(output_dir.glob("*.png"))
        assert len(image_files) == 0

    def test_save_output_with_none_metadata(self, tmp_path):
        """Test saving output with None metadata."""
        # Create PPTXOutput with None metadata
        text_data = ["Slide 1 content"]
        images_data = [[Image.new('RGB', (100, 100), color='white')]]
        
        output = PptxOutput(text_data, images_data, None)
        
        # Save output
        output_dir = tmp_path / "none_metadata_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "none_metadata_presentation")
        
        # Verify files were created
        assert (output_dir / "none_metadata_presentation.md").exists()
        assert (output_dir / "none_metadata_presentation_meta.json").exists()
        assert (output_dir / "Slide_0_image_0.png").exists()


class TestPPTXOutputEdgeCases:
    """Edge case tests for PPTXOutput."""

    def test_single_slide_with_multiple_images(self, tmp_path):
        """Test single slide with multiple images."""
        # Create PPTXOutput with single slide but multiple images
        text_data = ["Single slide with many images"]
        
        # Create 5 mock images for the single slide
        colors = ['white', 'lightgray', 'gray', 'darkgray', 'black']
        mock_images = [[Image.new('RGB', (100, 100), color=colors[i]) for i in range(5)]]
        
        metadata = {"title": "Many Images Presentation"}
        
        output = PptxOutput(text_data, mock_images, metadata)
        
        # Save output
        output_dir = tmp_path / "many_images_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "many_images_presentation")
        
        # Verify all image files were created
        for i in range(5):
            assert (output_dir / f"Slide_0_image_{i}.png").exists()

    def test_multiple_slides_no_images(self, tmp_path):
        """Test multiple slides with no images."""
        # Create PPTXOutput with multiple slides but no images
        text_data = [f"Slide {i} content" for i in range(5)]
        
        output = PptxOutput(text_data, [], {})
        
        # Save output
        output_dir = tmp_path / "multi_slide_no_images_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "multi_slide_no_images_presentation")
        
        # Verify markdown content has all slides
        md_file = output_dir / "multi_slide_no_images_presentation.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        for i in range(5):
            assert f"# Slide {i}" in md_content
            assert f"Slide {i} content" in md_content


class TestPPTXOutputErrorHandling:
    """Error handling tests for PPTXOutput."""

    def test_invalid_output_directory(self):
        """Test handling of invalid output directory."""
        # Create PPTXOutput
        output = PptxOutput(["test"], [], {})
        
        # Test with invalid directory
        with pytest.raises(Exception):
            output.save_output("/invalid/directory/path", "test")

    def test_file_write_permission_error(self, tmp_path):
        """Test handling of file write permission errors."""
        # Create PPTXOutput
        output = PptxOutput(["test"], [], {})
        
        # Create a directory with no write permissions (simulated)
        output_dir = tmp_path / "no_write_permissions"
        output_dir.mkdir()
        
        # Make directory read-only (on Unix-like systems)
        try:
            os.chmod(output_dir, 0o444)
            
            # Test file write should fail
            with pytest.raises((PermissionError, OSError)):
                output.save_output(str(output_dir), "test")
        finally:
            # Restore permissions
            os.chmod(output_dir, 0o755)

    def test_image_save_error(self, tmp_path):
        """Test handling of image save errors."""
        # Create PPTXOutput with mock image that raises error on save
        text_data = ["Test slide"]
        
        mock_image = Mock()
        mock_image.save.side_effect = Exception("Image save error")
        
        output = PptxOutput(text_data, [[mock_image]], {})
        
        # Save output
        output_dir = tmp_path / "image_error_output"
        output_dir.mkdir()
        
        # Should handle image save error gracefully
        with pytest.raises(Exception):
            output.save_output(str(output_dir), "image_error_presentation")


class TestPPTXOutputFileOperations:
    """Tests for file operations in PPTXOutput."""

    def test_file_naming_convention(self, tmp_path):
        """Test that files follow proper naming conventions."""
        # Create PPTXOutput with multiple slides and images
        text_data = ["Slide 1", "Slide 2", "Slide 3"]
        
        mock_images = [
            [Image.new('RGB', (100, 100), color='white'), Image.new('RGB', (100, 100), color='lightgray')],
            [Image.new('RGB', (100, 100), color='gray')],
            []  # Slide 3 has no images
        ]
        
        output = PptxOutput(text_data, mock_images, {})
        
        # Save output
        output_dir = tmp_path / "naming_test_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "naming_test")
        
        # Verify file naming
        assert (output_dir / "naming_test.md").exists()
        assert (output_dir / "naming_test_meta.json").exists()
        assert (output_dir / "Slide_0_image_0.png").exists()
        assert (output_dir / "Slide_0_image_1.png").exists()
        assert (output_dir / "Slide_1_image_0.png").exists()
        
        # Verify no files for slide 3 (no images)
        assert not (output_dir / "Slide_2_image_0.png").exists()

    def test_metadata_json_validation(self, tmp_path):
        """Test that metadata JSON is properly formatted."""
        # Create PPTXOutput with complex metadata
        complex_metadata = {
            "title": "Complex Presentation",
            "author": "Test Author",
            "date": "2024-03-24",
            "tags": ["test", "presentation"],
            "settings": {
                "theme": "dark",
                "transition": "slide"
            }
        }
        
        output = PptxOutput(["test"], [], complex_metadata)
        
        # Save output
        output_dir = tmp_path / "metadata_test_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "metadata_test")
        
        # Verify metadata JSON is valid and properly formatted
        meta_file = output_dir / "metadata_test_meta.json"
        with open(meta_file, 'r') as f:
            meta_content = json.load(f)
        
        assert meta_content == complex_metadata

    def test_markdown_format_validation(self, tmp_path):
        """Test that markdown output is properly formatted."""
        # Create PPTXOutput with multiple slides
        text_data = [
            "# Slide 1 Title\n\nSlide 1 content",
            "# Slide 2 Title\n\nSlide 2 content with **bold** text",
            "# Slide 3 Title\n\nSlide 3 content with `code`"
        ]
        
        output = PptxOutput(text_data, [], {})
        
        # Save output
        output_dir = tmp_path / "markdown_test_output"
        output_dir.mkdir()
        
        output.save_output(str(output_dir), "markdown_test")
        
        # Verify markdown format
        md_file = output_dir / "markdown_test.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        # Check that markdown structure is preserved
        assert "# Slide 0" in md_content
        assert "# Slide 1" in md_content
        assert "# Slide 2" in md_content
        assert "**bold**" in md_content
        assert "`code`" in md_content


if __name__ == "__main__":
    pytest.main([__file__])
