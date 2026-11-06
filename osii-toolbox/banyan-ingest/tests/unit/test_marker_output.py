"""
Unit tests for MarkerOutput class.

These tests verify the functionality of the MarkerOutput class
using mocking for file operations and external dependencies.
"""

import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Marker is an optional dependency, so we need to handle ImportError
try:
    from banyan_extract.output.marker_output import MarkerOutput
except ImportError:
    # Create a mock MarkerOutput class for testing when marker is not available
    from banyan_extract.output.output import ModelOutput
    
    class MarkerOutput(ModelOutput):
        def __init__(self, output_data):
            super().__init__(output_data)
            
        def save_output(self, output_dir, basename):
            pass
            
        def get_content(self):
            return ""
            
        def get_images(self):
            return []
            
        def get_tables(self):
            return []


class TestMarkerOutputInitialization:
    """Tests for MarkerOutput initialization."""

    def test_initialization_with_valid_data(self):
        """Test that MarkerOutput initializes correctly with valid output data."""
        # Create mock output_data
        mock_output_data = Mock()
        mock_output_data.markdown = "# Sample Markdown\n\nThis is sample text."
        mock_output_data.images = {"image1.png": MagicMock(), "image2.png": MagicMock()}
        mock_output_data.tables = [MagicMock(), MagicMock()]
        mock_output_data.metadata = {"pages": 2, "format": "markdown"}

        # Initialize MarkerOutput
        output = MarkerOutput(mock_output_data)

        # Verify initialization
        assert output.text == "# Sample Markdown\n\nThis is sample text."
        assert len(output.images) == 2
        assert len(output.tables) == 2
        assert output.metadata == {"pages": 2, "format": "markdown"}

    def test_initialization_with_empty_data(self):
        """Test initialization with empty or minimal data."""
        mock_output_data = Mock()
        mock_output_data.markdown = ""
        mock_output_data.images = {}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        assert output.text == ""
        assert len(output.images) == 0
        assert len(output.tables) == 0
        assert output.metadata == {}


class TestMarkerOutputSaveOutput:
    """Tests for MarkerOutput save_output method."""

    def test_save_output_success(self, tmp_path):
        """Test successful save_output operation."""
        # Create mock output_data
        mock_output_data = Mock()
        mock_output_data.markdown = "# Test Content\n\nThis is test content."
        mock_output_data.images = {
            "page1_image1.png": MagicMock(),
            "page2_image1.png": MagicMock()
        }
        mock_output_data.tables = [MagicMock()]
        mock_output_data.metadata = {"pages": 1, "source": "test.pdf"}

        output = MarkerOutput(mock_output_data)

        # Mock file operations
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.dumps') as mock_json_dumps:
                with patch('os.path.join', side_effect=lambda *args: os.path.join(*args)):
                    # Call save_output
                    output.save_output(str(tmp_path), "test_output")

                    # Verify markdown file was written
                    markdown_path = os.path.join(str(tmp_path), "test_output.md")
                    assert any(call[0][0] == markdown_path for call in mock_open.call_args_list)

                    # Verify metadata file was written
                    meta_path = os.path.join(str(tmp_path), "test_output_meta.json")
                    assert any(call[0][0] == meta_path for call in mock_open.call_args_list)

                    # Verify json.dumps was called with metadata
                    mock_json_dumps.assert_called_once_with(mock_output_data.metadata, indent=2)

    def test_save_output_with_empty_content(self, tmp_path):
        """Test save_output with empty content."""
        mock_output_data = Mock()
        mock_output_data.markdown = ""
        mock_output_data.images = {}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('builtins.open', create=True) as mock_open:
            with patch('json.dumps') as mock_json_dumps:
                output.save_output(str(tmp_path), "empty_output")

                # Should still create files even with empty content
                markdown_path = os.path.join(str(tmp_path), "empty_output.md")
                meta_path = os.path.join(str(tmp_path), "empty_output_meta.json")
                assert any(call[0][0] == markdown_path for call in mock_open.call_args_list)
                assert any(call[0][0] == meta_path for call in mock_open.call_args_list)

    def test_save_output_with_multiple_images(self, tmp_path):
        """Test save_output with multiple images."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        mock_output_data.images = {
            f"image_{i}.png": MagicMock() for i in range(5)
        }
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('os.path.join', side_effect=lambda *args: os.path.join(*args)):
            with patch.object(mock_output_data.images['image_0.png'], 'save') as mock_save:
                output.save_output(str(tmp_path), "multi_image")
                
                # Verify image save was called
                mock_save.assert_called_once()


class TestMarkerOutputEdgeCases:
    """Edge case tests for MarkerOutput."""


    def test_mixed_content_types(self):
        """Test handling of mixed content types in images and tables."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Mixed Content\n\nText with images and tables."
        
        # Create mock images and tables
        mock_images = {f"image_{i}.png": MagicMock() for i in range(3)}
        mock_tables = [MagicMock(), MagicMock()]
        
        mock_output_data.images = mock_images
        mock_output_data.tables = mock_tables
        mock_output_data.metadata = {"image_count": 3, "table_count": 2}

        output = MarkerOutput(mock_output_data)
        assert len(output.images) == 3
        assert len(output.tables) == 2


class TestMarkerOutputErrorHandling:
    """Tests for error handling in MarkerOutput."""

    def test_file_write_permission_error(self):
        """Test handling of file write permission errors."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        mock_output_data.images = {}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        # Mock open to raise permission error
        with patch('builtins.open', side_effect=PermissionError("No permission")):
            with pytest.raises(PermissionError):
                output.save_output("/invalid/path", "test")

    def test_invalid_output_directory(self):
        """Test handling of invalid output directory."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        mock_output_data.images = {}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        # This should raise an error when trying to write to non-existent directory
        with pytest.raises(FileNotFoundError):
            output.save_output("/nonexistent/directory/path", "test")

    def test_image_save_error(self, tmp_path):
        """Test handling of image save errors."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        
        # Create mock image that raises error on save
        mock_image = MagicMock()
        mock_image.save.side_effect = IOError("Cannot save image")
        
        mock_output_data.images = {"error_image.png": mock_image}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('builtins.open', create=True):
            with patch('json.dumps'):
                with pytest.raises(IOError):
                    output.save_output(str(tmp_path), "test")


class TestMarkerOutputFileOperations:
    """Tests for file operations in MarkerOutput."""

    def test_markdown_file_content(self, tmp_path):
        """Test that markdown file contains correct content."""
        mock_output_data = Mock()
        expected_markdown = "# Test Header\n\nParagraph text with **bold** and *italic*.\n\n- List item 1\n- List item 2"
        mock_output_data.markdown = expected_markdown
        mock_output_data.images = {}
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('builtins.open', create=True) as mock_open:
            mock_file_handle = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file_handle
            
            output.save_output(str(tmp_path), "test_markdown")
            
            # Verify the write call contains our markdown content
            mock_file_handle.write.assert_called_once_with(expected_markdown)

    def test_metadata_file_content(self, tmp_path):
        """Test that metadata file contains correct JSON content."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        mock_output_data.images = {}
        mock_output_data.tables = []
        expected_metadata = {
            "document": {"pages": 3, "source": "test.pdf"},
            "processing": {"time": 1.23, "model": "marker"}
        }
        mock_output_data.metadata = expected_metadata

        output = MarkerOutput(mock_output_data)

        with patch('builtins.open', create=True) as mock_open:
            with patch('json.dumps') as mock_json_dumps:
                mock_file_handle = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file_handle
                
                output.save_output(str(tmp_path), "test_metadata")
                
                # Verify json.dumps was called with correct metadata
                mock_json_dumps.assert_called_once_with(expected_metadata, indent=2)
                mock_file_handle.write.assert_called_once()

    def test_image_file_naming(self, tmp_path):
        """Test that image files are named correctly."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        
        # Create mock images
        mock_image1 = MagicMock()
        mock_image2 = MagicMock()
        
        mock_output_data.images = {
            "page1_image1.png": mock_image1,
            "page2_image1.png": mock_image2
        }
        mock_output_data.tables = []
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('os.path.join', side_effect=lambda *args: os.path.join(*args)):
            with patch.object(mock_image1, 'save') as mock_save1:
                with patch.object(mock_image2, 'save') as mock_save2:
                    output.save_output(str(tmp_path), "test_images")
                    
                    # Verify image save calls with correct filenames
                    expected_path1 = os.path.join(str(tmp_path), "test_images_page1_image1.png")
                    expected_path2 = os.path.join(str(tmp_path), "test_images_page2_image1.png")
                    
                    mock_save1.assert_called_once_with(expected_path1, 'PNG')
                    mock_save2.assert_called_once_with(expected_path2, 'PNG')

    def test_table_file_naming(self, tmp_path):
        """Test that table files are named correctly."""
        mock_output_data = Mock()
        mock_output_data.markdown = "# Content"
        mock_output_data.images = {}
        
        # Create mock tables
        mock_table1 = MagicMock()
        mock_table2 = MagicMock()
        mock_output_data.tables = [mock_table1, mock_table2]
        mock_output_data.metadata = {}

        output = MarkerOutput(mock_output_data)

        with patch('os.path.join', side_effect=lambda *args: os.path.join(*args)):
            with patch.object(mock_table1, 'to_csv') as mock_to_csv1:
                with patch.object(mock_table2, 'to_csv') as mock_to_csv2:
                    output.save_output(str(tmp_path), "test_tables")
                    
                    # Verify table to_csv calls with correct filenames
                    expected_path1 = os.path.join(str(tmp_path), "test_tables_table_0.csv")
                    expected_path2 = os.path.join(str(tmp_path), "test_tables_table_1.csv")
                    
                    mock_to_csv1.assert_called_once_with(expected_path1)
                    mock_to_csv2.assert_called_once_with(expected_path2)
