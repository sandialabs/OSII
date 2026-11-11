import pytest
from unittest.mock import patch, MagicMock
import subprocess
import os
from pathlib import Path
from banyan_extract.converter.libreoffice_converter import LibreOfficeConverter
from banyan_extract.converter.exceptions import (
    LibreOfficeNotFoundError,
    UnsupportedFormatError,
    ConversionTimeoutError,
    ConversionFailedError,
    CleanupFailedError
)

def test_init_valid_params(tmp_path):
    """Test initialization with valid parameters."""
    converter = LibreOfficeConverter(libreoffice_path="libreoffice", temp_dir=str(tmp_path), timeout=60)
    assert converter.libreoffice_path == "libreoffice"
    assert converter.timeout == 60
    assert converter.temp_dir == tmp_path

def test_init_invalid_timeout():
    """Test initialization with non-positive timeout."""
    with pytest.raises(ValueError, match="Timeout must be a positive integer"):
        LibreOfficeConverter(timeout=0)
    with pytest.raises(ValueError, match="Timeout must be a positive integer"):
        LibreOfficeConverter(timeout=-10)

def test_init_invalid_temp_dir():
    """Test initialization with non-existent or non-writable temp directory."""
    with pytest.raises(ValueError, match="must exist and be writable"):
        LibreOfficeConverter(temp_dir="/non/existent/path/to/temp")

@patch("subprocess.run")
def test_convert_to_pdf_success(mock_run, tmp_path):
    """Test successful conversion with proper mocking."""
    # Create a dummy input file
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    # Mock subprocess to simulate successful conversion
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = b""
    
    mock_run.return_value = mock_result
    
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    # Mock the PDF validation to return True
    with patch.object(converter, '_validate_pdf_output', return_value=True):
        # Also mock Path.exists to return True for the expected PDF
        with patch("pathlib.Path.exists") as mock_exists:
            # First call: input_path.exists() -> True
            # Second call: expected_pdf.exists() -> True
            mock_exists.side_effect = [True, True]
            
            result = converter.convert_to_pdf(str(input_file))
            
            # Verify the command was called correctly
            assert mock_run.called
            args = mock_run.call_args[0][0]
            assert args[0] == "libreoffice"
            assert "--headless" in args
            assert "--convert-to" in args
            assert "pdf" in args
            
            # Verify result is a valid path
            assert Path(result).exists
            assert Path(result).suffix == ".pdf"

@patch("subprocess.run")
def test_convert_to_pdf_invalid_output(mock_run, tmp_path):
    """Test that invalid PDF output is detected."""
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    # Mock subprocess to simulate successful conversion
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = b""
    
    mock_run.return_value = mock_result
    
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    # Mock the PDF validation to return False (invalid PDF)
    with patch.object(converter, '_validate_pdf_output', return_value=False):
        with pytest.raises(ConversionFailedError):
            converter.convert_to_pdf(str(input_file))

@patch("subprocess.run")
def test_convert_to_pdf_libreoffice_not_found(mock_run, tmp_path):
    """Test proper error when LibreOffice is not found."""
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    # Mock subprocess.run to raise FileNotFoundError
    mock_run.side_effect = FileNotFoundError()
    
    converter = LibreOfficeConverter(libreoffice_path="libreoffice", temp_dir=str(tmp_path))
    
    # Don't mock Path.exists - the file actually exists
    # Mock os.access to return True for readability check
    with patch("os.access") as mock_access:
        mock_access.return_value = True
        
        # The test should raise LibreOfficeNotFoundError when FileNotFoundError
        # contains the libreoffice_path in the error message
        # Since we can't easily control the error message in the mock,
        # let's test that the general FileNotFoundError handling works
        with pytest.raises(LibreOfficeNotFoundError):
            converter.convert_to_pdf(str(input_file))

def test_convert_to_pdf_input_file_not_found(tmp_path):
    """Test proper error when input file is not found."""
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    with pytest.raises(FileNotFoundError):
        converter.convert_to_pdf("/nonexistent/file.docx")

def test_validate_pdf_output_valid(tmp_path):
    """Test PDF validation with a valid PDF."""
    # Create a minimal valid PDF
    pdf_file = tmp_path / "valid.pdf"
    pdf_file.write_bytes(b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF')
    
    converter = LibreOfficeConverter()
    assert converter._validate_pdf_output(pdf_file) is True

def test_validate_pdf_output_invalid(tmp_path):
    """Test PDF validation with an invalid file."""
    # Create an invalid file
    invalid_file = tmp_path / "invalid.pdf"
    invalid_file.write_text("not a pdf")
    
    converter = LibreOfficeConverter()
    assert converter._validate_pdf_output(invalid_file) is False

def test_validate_pdf_output_too_small(tmp_path):
    """Test PDF validation with a file that's too small."""
    # Create a file that's too small to be a valid PDF
    small_file = tmp_path / "small.pdf"
    small_file.write_bytes(b'%PDF')  # Only 4 bytes
    
    converter = LibreOfficeConverter()
    assert converter._validate_pdf_output(small_file) is False


@patch("subprocess.run")
def test_convert_to_pdf_libreoffice_not_found(mock_run, tmp_path):
    """Test when LibreOffice executable is not found."""
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    mock_run.side_effect = FileNotFoundError
    
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    with pytest.raises(LibreOfficeNotFoundError):
        converter.convert_to_pdf(str(input_file))

@patch("subprocess.run")
def test_convert_to_pdf_timeout(mock_run, tmp_path):
    """Test conversion timeout."""
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="libreoffice", timeout=120)
    
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    with pytest.raises(ConversionTimeoutError):
        converter.convert_to_pdf(str(input_file))

@patch("subprocess.run")
def test_convert_to_pdf_failure(mock_run, tmp_path):
    """Test conversion failure with non-zero exit code."""
    input_file = tmp_path / "test.docx"
    input_file.write_text("dummy content")
    
    mock_run.return_value = MagicMock(returncode=1, stderr=b"Error occurred")
    
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    with pytest.raises(ConversionFailedError):
        converter.convert_to_pdf(str(input_file))

def test_cleanup_all(tmp_path):
    """Test that cleanup() removes all managed directories."""
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    # Manually add some managed dirs
    dir1 = tmp_path / "banyan_1"
    dir1.mkdir()
    dir2 = tmp_path / "banyan_2"
    dir2.mkdir()
    converter._managed_dirs.add(dir1)
    converter._managed_dirs.add(dir2)
    
    converter.cleanup()
    
    assert not dir1.exists()
    assert not dir2.exists()
    assert len(converter._managed_dirs) == 0

def test_cleanup_single_file(tmp_path):
    """Test that cleanup(pdf_filepath) removes the specific managed directory."""
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    dir1 = tmp_path / "banyan_1"
    dir1.mkdir()
    pdf1 = dir1 / "test1.pdf"
    pdf1.write_text("pdf1")
    
    dir2 = tmp_path / "banyan_2"
    dir2.mkdir()
    pdf2 = dir2 / "test2.pdf"
    pdf2.write_text("pdf2")
    
    converter._managed_dirs.add(dir1)
    converter._managed_dirs.add(dir2)
    
    converter.cleanup(str(pdf1))
    
    assert not dir1.exists()
    assert dir2.exists()
    assert dir2 in converter._managed_dirs
    assert dir1 not in converter._managed_dirs

def test_cleanup_failure(tmp_path):
    """Test that cleanup failures raise CleanupFailedError."""
    converter = LibreOfficeConverter(temp_dir=str(tmp_path))
    
    # Create a managed directory
    managed_dir = tmp_path / "banyan_test"
    managed_dir.mkdir()
    converter._managed_dirs.add(managed_dir)
    
    # Mock shutil.rmtree to raise an exception
    with patch("shutil.rmtree") as mock_rmtree:
        mock_rmtree.side_effect = OSError("Mocked cleanup failure")
        
        with pytest.raises(CleanupFailedError):
            converter.cleanup()

def test_context_manager_cleanup(tmp_path):
    """Test that the context manager triggers cleanup."""
    with LibreOfficeConverter(temp_dir=str(tmp_path)) as converter:
        dir1 = tmp_path / "banyan_1"
        dir1.mkdir()
        converter._managed_dirs.add(dir1)
        assert dir1.exists()
        
    assert not dir1.exists()

