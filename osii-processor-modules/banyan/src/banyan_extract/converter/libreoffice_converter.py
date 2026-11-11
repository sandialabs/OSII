import os
import subprocess
import tempfile
import uuid
import logging
import shutil
import shlex
from pathlib import Path
from .exceptions import (
    LibreOfficeConversionError,
    LibreOfficeNotFoundError,
    UnsupportedFormatError,
    ConversionTimeoutError,
    ConversionFailedError,
    CleanupFailedError
)

logger = logging.getLogger(__name__)

class LibreOfficeConverter:
    """
    Converts Office documents to PDF using LibreOffice command-line interface.
    
    Handles DOCX, PPTX, XLSX -> PDF conversion with temporary file management.
    """
    
    def __init__(self, 
                 libreoffice_path: str = "libreoffice", 
                 temp_dir: str = None, 
                 cleanup_temp_files: bool = True, 
                 timeout: int = 120):
        """
        Initialize LibreOffice converter.
        """
        if timeout <= 0:
            raise ValueError("Timeout must be a positive integer")
            
        self.libreoffice_path = libreoffice_path
        
        # Validate and set temp_dir
        base_temp = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
        if not base_temp.exists() or not os.access(base_temp, os.W_OK):
            raise ValueError(f"Temporary directory {base_temp} must exist and be writable")
        
        self.temp_dir = base_temp
        self.cleanup_temp_files = cleanup_temp_files
        self.timeout = timeout
        self._managed_dirs = set()

    def _validate_pdf_output(self, pdf_path: Path) -> bool:
        """
        Validate that the output file is a valid PDF.
        
        Args:
            pdf_path: Path to the file to validate
            
        Returns:
            True if the file appears to be a valid PDF, False otherwise
        """
        try:
            # Check file exists and has minimum PDF size
            if not pdf_path.exists() or pdf_path.stat().st_size < 10:
                return False
            
            # Check PDF magic number (first 4 bytes should be %PDF)
            with open(pdf_path, 'rb') as f:
                header = f.read(4)
                return header == b'%PDF'
        except Exception as e:
            logger.warning(f"PDF validation failed for {pdf_path}: {e}")
            return False

    def convert_to_pdf(self, input_filepath: str) -> str:
        """
        Convert Office document to PDF.
        """
        input_path = Path(input_filepath)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_filepath}")
            
        if not os.access(input_path, os.R_OK):
            raise PermissionError(f"Input file not readable: {input_filepath}")
            
        supported_extensions = {'.docx', '.pptx', '.xlsx', '.doc', '.ppt', '.xls'}
        if input_path.suffix.lower() not in supported_extensions:
            raise UnsupportedFormatError(f"Unsupported file extension: {input_path.suffix}")
        
        # Prepare temporary output directory and filename
        session_id = uuid.uuid4().hex
        outdir = self.temp_dir / f"banyan_{session_id}"
        outdir.mkdir(parents=True, exist_ok=True)
        self._managed_dirs.add(outdir)
        
        # LibreOffice generates the PDF with the same basename as the input
        expected_pdf = outdir / f"{input_path.stem}.pdf"
        
        # Build command with proper argument escaping
        command = [
            self.libreoffice_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(outdir),
            str(input_path)
        ]
        
        # Escape all arguments to prevent shell injection
        safe_command = [shlex.quote(arg) for arg in command]
        
        try:
            logger.info(f"Executing: {' '.join(safe_command)}")
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=self.timeout,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr.decode()}")
                raise ConversionFailedError(f"LibreOffice returned exit code {result.returncode}")
                
        except FileNotFoundError as e:
            # Distinguish between input file not found and LibreOffice not found
            # If the error message is empty or contains the libreoffice path, assume it's LibreOffice not found
            error_str = str(e)
            if not error_str or self.libreoffice_path in error_str:
                raise LibreOfficeNotFoundError(f"LibreOffice executable not found at: {self.libreoffice_path}")
            else:
                # Re-raise original FileNotFoundError for input file issues
                raise
        except subprocess.TimeoutExpired:
            raise ConversionTimeoutError(f"Conversion exceeded timeout of {self.timeout}s")
        except Exception as e:
            if not isinstance(e, (LibreOfficeConversionError, FileNotFoundError, PermissionError)):
                logger.error(f"Unexpected error during conversion: {e}")
                raise ConversionFailedError(f"An unexpected error occurred: {e}")
            raise
        
        if not expected_pdf.exists():
            raise ConversionFailedError("LibreOffice finished but output PDF was not created")
        
        # Validate the output PDF
        if not self._validate_pdf_output(expected_pdf):
            raise ConversionFailedError(f"Output file {expected_pdf} is not a valid PDF")
        
        return str(expected_pdf.absolute())

    def cleanup(self, pdf_filepath: str = None):
        """
        Clean up temporary files.
        """
        try:
            if pdf_filepath:
                pdf_path = Path(pdf_filepath)
                if pdf_path.exists():
                    # Only remove if it's in one of our managed dirs
                    parent = pdf_path.parent
                    if parent in self._managed_dirs:
                        shutil.rmtree(parent, ignore_errors=True)
                        self._managed_dirs.remove(parent)
            else:
                # Clean up all managed directories
                for managed_dir in list(self._managed_dirs):
                    if managed_dir.exists():
                        shutil.rmtree(managed_dir, ignore_errors=True)
                self._managed_dirs.clear()
        except Exception as e:
            logger.error(f"Failed to cleanup temporary files: {e}")
            raise CleanupFailedError(f"Cleanup failed: {e}") from e


    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cleanup_temp_files:
            self.cleanup()
        return False

