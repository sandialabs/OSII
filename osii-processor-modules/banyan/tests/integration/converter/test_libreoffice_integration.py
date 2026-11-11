import pytest
import shutil
import subprocess
from pathlib import Path
from banyan_extract.converter.libreoffice_converter import LibreOfficeConverter
from banyan_extract.converter.exceptions import LibreOfficeNotFoundError

def is_libreoffice_installed():
    """Check if LibreOffice is available in the system path."""
    for cmd in ["libreoffice", "soffice"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False

# Mark tests as optional based on installation
pytestmark = pytest.mark.skipif(
    not is_libreoffice_installed(), 
    reason="LibreOffice not installed on this system"
)

def create_dummy_office_file(path: Path):
    """
    Creates a very basic file that LibreOffice can attempt to convert.
    Note: These are not 'valid' OOXML files but often enough for 
    LibreOffice to process or at least try to convert.
    """
    # A minimal DOCX is actually a ZIP of XMLs. 
    # For a true integration test, we'd need actual sample files.
    # Since we can't easily generate a valid .docx here, we'll create 
    # a simple text file and rename it to .docx. 
    # LibreOffice is often lenient enough to convert these.
    path.write_text("This is a dummy document for integration testing.")

@pytestmark
def test_integration_convert_docx_to_pdf(tmp_path):
    """Test actual conversion of a dummy DOCX file."""
    input_file = tmp_path / "test_doc.docx"
    create_dummy_office_file(input_file)
    
    with LibreOfficeConverter(temp_dir=str(tmp_path)) as converter:
        pdf_path = converter.convert_to_pdf(str(input_file))
        
        assert Path(pdf_path).exists()
        assert Path(pdf_path).suffix == ".pdf"

@pytestmark
def test_integration_convert_xlsx_to_pdf(tmp_path):
    """Test actual conversion of a dummy XLSX file."""
    input_file = tmp_path / "test_sheet.xlsx"
    create_dummy_office_file(input_file)
    
    with LibreOfficeConverter(temp_dir=str(tmp_path)) as converter:
        pdf_path = converter.convert_to_pdf(str(input_file))
        
        assert Path(pdf_path).exists()
        assert Path(pdf_path).suffix == ".pdf"

@pytestmark
def test_integration_convert_pptx_to_pdf(tmp_path):
    """Test actual conversion of a dummy PPTX file."""
    input_file = tmp_path / "test_pres.pptx"
    create_dummy_office_file(input_file)
    
    with LibreOfficeConverter(temp_dir=str(tmp_path)) as converter:
        pdf_path = converter.convert_to_pdf(str(input_file))
        
        assert Path(pdf_path).exists()
        assert Path(pdf_path).suffix == ".pdf"
