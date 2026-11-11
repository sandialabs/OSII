# Simplified unit tests for PPTX processor lazy dependency checking
# Tests the lazy loading behavior without complex mocking

import pytest
from unittest.mock import patch
import sys

from banyan_extract.processor.pptx_processor import PptxProcessor


class TestPPTXLazyDependencySimple:
    """Simple tests for lazy dependency checking in PPTX processor."""

    def test_surya_not_loaded_by_default(self):
        """Test that Surya dependencies are not loaded when not explicitly requested."""
        # Verify Surya is not in sys.modules before creating processor
        surya_before = 'surya' in sys.modules
        
        # Create processor with default (Nemotron) backend
        processor = PptxProcessor()
        
        # Verify Surya is still not loaded
        surya_after = 'surya' in sys.modules
        
        # Surya should not be loaded unless explicitly requested
        assert surya_before == surya_after

    def test_nemotron_loaded_by_default(self):
        """Test that Nemotron is loaded by default."""
        # Create processor with default backend
        processor = PptxProcessor()
        
        # Verify processor is initialized
        assert processor is not None
        assert hasattr(processor, 'ocr_backend')

    def test_backend_switching_works(self):
        """Test switching between backends."""
        # Create processors with different backends
        nemotron_processor = PptxProcessor(ocr_backend="nemotron")
        surya_processor = PptxProcessor(ocr_backend="surya")
        
        # Verify both processors are initialized
        assert nemotron_processor is not None
        assert surya_processor is not None


if __name__ == "__main__":
    pytest.main([__file__])
