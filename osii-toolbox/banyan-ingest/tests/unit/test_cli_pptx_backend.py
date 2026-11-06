# Unit tests for CLI PPTX backend argument parsing

import pytest
from unittest.mock import patch

from banyan_extract.cli import parse_arguments


class TestCLIPptxBackendArguments:
    """Test CLI argument parsing for PPTX backend-related features."""
    
    def test_pptx_ocr_backend_default(self):
        """Test that the default PPTX OCR backend is now nemotron."""
        with patch('sys.argv', ['banyan_extract', 'input.pptx', 'output/']):
            args = parse_arguments()
            assert args.pptx_ocr_backend == "nemotron"
    
    def test_pptx_ocr_backend_explicit_nemotron(self):
        """Test explicit nemotron backend selection."""
        with patch('sys.argv', ['banyan_extract', 'input.pptx', 'output/', '--pptx_ocr_backend', 'nemotron']):
            args = parse_arguments()
            assert args.pptx_ocr_backend == "nemotron"
    
    def test_pptx_ocr_backend_explicit_surya(self):
        """Test explicit surya backend selection."""
        with patch('sys.argv', ['banyan_extract', 'input.pptx', 'output/', '--pptx_ocr_backend', 'surya']):
            args = parse_arguments()
            assert args.pptx_ocr_backend == "surya"


if __name__ == "__main__":
    pytest.main([__file__])