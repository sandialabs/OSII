"""
Unit tests for PaperMageOutput class.

These tests verify the functionality of the PaperMageOutput class
using mocking for file operations and external dependencies.
"""

import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from banyan_extract.output.papermage_output import PaperMageOutput


class TestPapermageOutputInitialization:
    """Tests for PaperMageOutput initialization."""

    def test_initialization_with_valid_data(self, capsys):
        """Test that PaperMageOutput initializes correctly with valid output data."""
        # Create mock output_data
        mock_output_data = Mock()
        
        # Initialize PaperMageOutput
        output = PaperMageOutput(mock_output_data)

        # Verify initialization
        assert output.output_data == mock_output_data
        
        # Check that the output_data was printed (as per the class implementation)
        captured = capsys.readouterr()
        assert str(mock_output_data) in captured.out

    def test_initialization_with_none_data(self):
        """Test initialization with None data."""
        output = PaperMageOutput(None)
        assert output.output_data is None

    def test_initialization_with_empty_data(self):
        """Test initialization with empty data structures."""
        mock_output_data = Mock()
        mock_output_data.__str__ = Mock(return_value="Empty data")
        
        output = PaperMageOutput(mock_output_data)
        assert output.output_data == mock_output_data


class TestPapermageOutputSaveOutput:
    """Tests for PaperMageOutput save_output method."""

    def test_save_output_bound_single_mode(self, tmp_path):
        """Test save_output in bound_single mode."""
        # Create mock output_data with plotted images
        mock_plotted1 = MagicMock()
        mock_plotted2 = MagicMock()
        mock_output_data = [mock_plotted1, mock_plotted2]
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path') as mock_path:
            # Mock the path operations
            mock_save_path = MagicMock()
            mock_path.return_value = mock_save_path
            
            # Call save_output in bound_single mode
            output.save_output(str(tmp_path), "test_output", "bound_single")
            
            # Verify the save calls
            mock_plotted1.save.assert_called_once()
            mock_plotted2.save.assert_called_once()

    def test_save_output_bound_batch_mode(self, tmp_path):
        """Test save_output in bound_batch mode."""
        # Create mock output_data for batch mode
        mock_plotted1 = MagicMock()
        mock_plotted2 = MagicMock()
        mock_output_data = {
            "file1.pdf": [mock_plotted1],
            "file2.pdf": [mock_plotted2]
        }
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path') as mock_path_class:
            # Mock the Path class and its instances
            mock_save_path = MagicMock()
            mock_file_path1 = MagicMock()
            mock_file_path2 = MagicMock()
            
            # Track calls to Path constructor
            path_instances = []
            
            def path_side_effect(arg):
                if isinstance(arg, str) and arg.startswith(str(tmp_path)):
                    return mock_save_path
                elif isinstance(arg, str) and "file1.pdf" in arg:
                    return mock_file_path1
                elif isinstance(arg, str) and "file2.pdf" in arg:
                    return mock_file_path2
                # For pathlib.Path(save_path / file) calls
                mock_new_path = MagicMock()
                path_instances.append(mock_new_path)
                return mock_new_path
            
            mock_path_class.side_effect = path_side_effect
            
            # Mock the __truediv__ method to return appropriate paths
            def truediv_side_effect(other):
                if "file1.pdf" in str(other):
                    return mock_file_path1
                elif "file2.pdf" in str(other):
                    return mock_file_path2
                # For the actual file paths inside the directories
                if isinstance(other, str) and other.startswith("test_output_page_"):
                    mock_file = MagicMock()
                    mock_file.__str__ = Mock(return_value=f"/{other}")
                    return mock_file
                return MagicMock()
            
            mock_save_path.__truediv__ = MagicMock(side_effect=truediv_side_effect)
            mock_file_path1.__truediv__ = MagicMock(side_effect=truediv_side_effect)
            mock_file_path2.__truediv__ = MagicMock(side_effect=truediv_side_effect)
            
            # Call save_output in bound_batch mode
            output.save_output(str(tmp_path), "test_output", "bound_batch")
            
            # Verify directory creation and save calls
            # The mkdir should be called on the pathlib.Path(save_path / file) instances
            for path_instance in path_instances:
                path_instance.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            
            mock_plotted1.save.assert_called_once()
            mock_plotted2.save.assert_called_once()

    def test_save_output_extract_single_mode(self, tmp_path):
        """Test save_output in extract_single mode."""
        # Create mock output_data for extract mode
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {"pages": [{"content": "test"}]}
        mock_output_data.get_layer.return_value = ["layer1", "layer2"]
        
        output = PaperMageOutput(mock_output_data)
        
        options = ["text", "tables"]
        
        with patch('pathlib.Path') as mock_path:
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    
                    mock_save_path = MagicMock()
                    mock_path.return_value = mock_save_path
                    
                    # Mock file handles
                    mock_file_handle = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file_handle
                    
                    # Call save_output in extract_single mode
                    output.save_output(str(tmp_path), "test_output", "extract_single", options)
                    
                    # Verify JSON dump was called
                    mock_json_dump.assert_called_once()
                    
                    # Verify layer files were created
                    assert mock_open.call_count == 3  # 1 JSON + 2 layer files

    def test_save_output_extract_batch_mode(self, tmp_path):
        """Test save_output in extract_batch mode."""
        # Create mock output_data for batch extract mode
        mock_extracted1 = MagicMock()
        mock_extracted1.to_json.return_value = {"pages": [{"content": "file1"}]}
        mock_extracted1.get_layer.return_value = ["layer1"]
        
        mock_extracted2 = MagicMock()
        mock_extracted2.to_json.return_value = {"pages": [{"content": "file2"}]}
        mock_extracted2.get_layer.return_value = ["layer2"]
        
        mock_output_data = {
            "file1.pdf": mock_extracted1,
            "file2.pdf": mock_extracted2
        }
        
        output = PaperMageOutput(mock_output_data)
        
        options = ["text"]
        
        with patch('pathlib.Path') as mock_path_class:
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    
                    mock_save_path = MagicMock()
                    mock_file_path1 = MagicMock()
                    mock_file_path2 = MagicMock()
                    
                    # Track calls to Path constructor
                    path_instances = []
                    
                    def path_side_effect(arg):
                        if isinstance(arg, str) and arg.startswith(str(tmp_path)):
                            return mock_save_path
                        elif isinstance(arg, str) and "file1.pdf" in arg:
                            return mock_file_path1
                        elif isinstance(arg, str) and "file2.pdf" in arg:
                            return mock_file_path2
                        # For pathlib.Path(save_path / file) calls
                        mock_new_path = MagicMock()
                        path_instances.append(mock_new_path)
                        return mock_new_path
                    
                    mock_path_class.side_effect = path_side_effect
                    
                    # Mock the __truediv__ method to return appropriate paths
                    def truediv_side_effect(other):
                        if "file1.pdf" in str(other):
                            return mock_file_path1
                        elif "file2.pdf" in str(other):
                            return mock_file_path2
                        return MagicMock()
                    
                    mock_save_path.__truediv__ = MagicMock(side_effect=truediv_side_effect)
                    mock_file_path1.__truediv__ = MagicMock(side_effect=truediv_side_effect)
                    mock_file_path2.__truediv__ = MagicMock(side_effect=truediv_side_effect)
                    
                    # Mock file handles
                    mock_file_handle = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file_handle
                    
                    # Call save_output in extract_batch mode
                    output.save_output(str(tmp_path), "test_output", "extract_batch", options)
                    
                    # Verify directory creation
                    # The mkdir should be called on the pathlib.Path(save_path / file) instances
                    for path_instance in path_instances:
                        path_instance.mkdir.assert_called_once_with(parents=True, exist_ok=True)
                    
                    # Verify JSON dumps were called
                    assert mock_json_dump.call_count == 2
                    
                    # Verify layer files were created
                    assert mock_open.call_count == 4  # 2 JSON + 2 layer files


class TestPapermageOutputEdgeCases:
    """Edge case tests for PaperMageOutput."""

    def test_empty_output_data_list(self, tmp_path):
        """Test handling of empty output data list."""
        mock_output_data = []
        output = PaperMageOutput(mock_output_data)
        
        # Should not raise an error with empty list
        output.save_output(str(tmp_path), "empty", "bound_single")

    def test_empty_output_data_dict(self, tmp_path):
        """Test handling of empty output data dictionary."""
        mock_output_data = {}
        output = PaperMageOutput(mock_output_data)
        
        # Should not raise an error with empty dict
        output.save_output(str(tmp_path), "empty", "bound_batch")

    def test_none_options_parameter(self, tmp_path):
        """Test handling of None options parameter."""
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {}
        mock_output_data.get_layer.return_value = []
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path'):
            with patch('builtins.open', create=True):
                with patch('json.dump'):
                    # Should handle None options gracefully
                    output.save_output(str(tmp_path), "test", "extract_single", None)

    def test_empty_options_list(self, tmp_path):
        """Test handling of empty options list."""
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {}
        mock_output_data.get_layer.return_value = []
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path'):
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    # Should handle empty options list
                    output.save_output(str(tmp_path), "test", "extract_single", [])
                    
                    # Should still create JSON file but no layer files
                    mock_json_dump.assert_called_once()
                    assert mock_open.call_count == 1


class TestPapermageOutputErrorHandling:
    """Tests for error handling in PaperMageOutput."""

    def test_invalid_mode(self, tmp_path):
        """Test handling of invalid mode parameter."""
        mock_output_data = Mock()
        output = PaperMageOutput(mock_output_data)
        
        # Invalid mode should not cause errors but also not do anything
        output.save_output(str(tmp_path), "test", "invalid_mode")

    def test_file_write_permission_error(self, tmp_path):
        """Test handling of file write permission errors."""
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {}
        mock_output_data.get_layer.return_value = []
        
        output = PaperMageOutput(mock_output_data)
        
        # Mock open to raise permission error
        with patch('builtins.open', side_effect=PermissionError("No permission")):
            with pytest.raises(PermissionError):
                output.save_output(str(tmp_path), "test", "extract_single")

    def test_invalid_output_directory(self, tmp_path):
        """Test handling of invalid output directory."""
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {}
        mock_output_data.get_layer.return_value = []
        
        output = PaperMageOutput(mock_output_data)
        
        # This should raise an error when trying to write to non-existent directory
        with pytest.raises(FileNotFoundError):
            output.save_output(str(tmp_path / "nonexistent"), "test", "extract_single")

    def test_image_save_error(self, tmp_path):
        """Test handling of image save errors in bound modes."""
        # Create mock plotted image that raises error on save
        mock_plotted = MagicMock()
        mock_plotted.save.side_effect = IOError("Cannot save image")
        
        mock_output_data = [mock_plotted]
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path'):
            with pytest.raises(IOError):
                output.save_output(str(tmp_path), "test", "bound_single")


class TestPapermageOutputFileOperations:
    """Tests for file operations in PaperMageOutput."""

    def test_bound_single_file_naming(self, tmp_path):
        """Test that bound_single mode creates correctly named files."""
        mock_plotted1 = MagicMock()
        mock_plotted2 = MagicMock()
        mock_output_data = [mock_plotted1, mock_plotted2]
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path') as mock_path_class:
            mock_save_path = MagicMock()
            mock_path_class.return_value = mock_save_path
            
            # Track the paths created for each page
            page_paths = []
            
            def truediv_side_effect(other):
                mock_path_obj = MagicMock()
                if isinstance(other, str) and other.startswith("test_output_page_"):
                    page_num = other.split("_")[-1].split(".")[0]
                    mock_path_obj.__str__ = Mock(return_value=f"{tmp_path}/test_output_page_{page_num}.png")
                    page_paths.append((int(page_num), mock_path_obj))
                return mock_path_obj
            
            mock_save_path.__truediv__ = Mock(side_effect=truediv_side_effect)
            
            output.save_output(str(tmp_path), "test_output", "bound_single")
            
            # Verify the save calls with correct filenames
            calls = mock_plotted1.save.call_args_list + mock_plotted2.save.call_args_list
            assert len(calls) == 2
            
            # Sort page_paths by page number to match call order
            page_paths.sort(key=lambda x: x[0])
            
            # Check that filenames follow the pattern: test_output_page_1.png, test_output_page_2.png
            for i, (page_num, path_obj) in enumerate(page_paths):
                expected_filename = f"test_output_page_{i+1}.png"
                assert expected_filename in str(path_obj)

    def test_extract_single_file_naming(self, tmp_path):
        """Test that extract_single mode creates correctly named files."""
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {"test": "data"}
        mock_output_data.get_layer.return_value = ["content"]
        
        output = PaperMageOutput(mock_output_data)
        
        options = ["text", "tables"]
        
        with patch('pathlib.Path') as mock_path:
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    
                    mock_save_path = MagicMock()
                    mock_path.return_value = mock_save_path
                    
                    output.save_output(str(tmp_path), "test_output", "extract_single", options)
                    
                    # Verify JSON file naming
                    json_call = mock_open.call_args_list[0]
                    expected_json_path = str(mock_save_path / "test_output.json")
                    assert expected_json_path in str(json_call)
                    
                    # Verify layer file naming
                    layer_calls = mock_open.call_args_list[1:]
                    for i, option in enumerate(options):
                        expected_layer_path = str(mock_save_path / f"test_output_{option}.txt")
                        assert expected_layer_path in str(layer_calls[i])

    def test_json_content_validation(self, tmp_path):
        """Test that JSON content is properly written."""
        expected_json_data = {
            "pages": [
                {
                    "page_number": 1,
                    "elements": [
                        {"type": "text", "content": "Sample text"}
                    ]
                }
            ],
            "metadata": {"source": "test.pdf", "pages": 1}
        }
        
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = expected_json_data
        mock_output_data.get_layer.return_value = []
        
        output = PaperMageOutput(mock_output_data)
        
        with patch('pathlib.Path'):
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    
                    output.save_output(str(tmp_path), "test", "extract_single")
                    
                    # Verify json.dump was called with correct data
                    # The call includes the file handle as second argument, so we need to check differently
                    assert mock_json_dump.call_count == 1
                    call_args = mock_json_dump.call_args
                    assert call_args[0][0] == expected_json_data  # First positional arg is the data
                    assert call_args[1].get('indent') == 2  # indent keyword arg

    def test_layer_content_validation(self, tmp_path):
        """Test that layer content is properly written."""
        expected_layer_data = ["text line 1", "text line 2", "text line 3"]
        
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {}
        mock_output_data.get_layer.return_value = expected_layer_data
        
        output = PaperMageOutput(mock_output_data)
        
        options = ["text"]
        
        with patch('pathlib.Path'):
            with patch('builtins.open', create=True) as mock_open:
                
                mock_file_handle = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file_handle
                
                output.save_output(str(tmp_path), "test", "extract_single", options)
                
                # Verify write calls contain the layer data
                write_calls = mock_file_handle.write.call_args_list
                layer_writes = [call for call in write_calls if "text line" in str(call)]
                
                # Should have written each element followed by newline
                assert len(layer_writes) == 3
                for i, expected_line in enumerate(expected_layer_data):
                    assert expected_line in str(layer_writes[i])


class TestPapermageOutputIntegration:
    """Integration-style tests for PaperMageOutput."""

    def test_complete_bound_single_workflow(self, tmp_path):
        """Test a complete workflow for bound_single mode."""
        # Create realistic mock data
        mock_plotted_pages = []
        for i in range(3):
            mock_page = MagicMock()
            mock_page.save = MagicMock()
            mock_plotted_pages.append(mock_page)
        
        output = PaperMageOutput(mock_plotted_pages)
        
        with patch('pathlib.Path') as mock_path:
            mock_save_path = MagicMock()
            mock_path.return_value = mock_save_path
            
            # Execute complete workflow
            output.save_output(str(tmp_path), "complete_test", "bound_single")
            
            # Verify all pages were saved
            for mock_page in mock_plotted_pages:
                mock_page.save.assert_called_once()

    def test_complete_extract_single_workflow(self, tmp_path):
        """Test a complete workflow for extract_single mode."""
        # Create realistic mock data
        mock_output_data = MagicMock()
        mock_output_data.to_json.return_value = {
            "document": "test.pdf",
            "pages": 5,
            "content": "extracted content"
        }
        mock_output_data.get_layer.return_value = [
            "Header text",
            "Body text", 
            "Footer text"
        ]
        
        output = PaperMageOutput(mock_output_data)
        options = ["text", "headers", "footers"]
        
        with patch('pathlib.Path'):
            with patch('builtins.open', create=True) as mock_open:
                with patch('json.dump') as mock_json_dump:
                    
                    # Execute complete workflow
                    output.save_output(str(tmp_path), "complete_extract", "extract_single", options)
                    
                    # Verify JSON file was created
                    mock_json_dump.assert_called_once()
                    
                    # Verify layer files were created (1 JSON + 3 layer files)
                    assert mock_open.call_count == 4
