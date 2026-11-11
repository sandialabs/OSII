# Integration tests for CLI PPTX backend functionality

import pytest
from unittest.mock import patch

from banyan_extract.cli import parse_arguments


class TestCLIPptxIntegration:
    """Integration tests for CLI PPTX backend functionality."""
    
    def test_cli_pptx_default_backend_parsing(self):
        """Test that CLI correctly parses default PPTX backend."""
        with patch('sys.argv', ['banyan_extract', 'test.pptx', 'output/']):
            args = parse_arguments()
            assert args.pptx_ocr_backend == "nemotron"
    
    def test_cli_pptx_explicit_backend_parsing(self):
        """Test that CLI correctly parses explicit PPTX backend."""
        with patch('sys.argv', ['banyan_extract', 'test.pptx', 'output/', '--pptx_ocr_backend', 'surya']):
            args = parse_arguments()
            assert args.pptx_ocr_backend == "surya"


if __name__ == "__main__":
    pytest.main([__file__])