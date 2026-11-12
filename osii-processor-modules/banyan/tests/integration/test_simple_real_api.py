"""
Simple real API tests that process documents and compare saved outputs with expected files.
Proper testing approach: process files, save outputs, compare with expected files.
"""

import pytest
import os
from pathlib import Path


class TestSimpleRealAPI:
    """Simple real API tests using actual documents from tests/data/docs/."""

    def test_process_sample_pdf(self, api_test_mode, temp_output_dir, test_data_dir):
        """Test processing sample.pdf and compare saved output with expected files."""
        # Only run this test when in real API mode
        if api_test_mode != 'real':
            pytest.skip(f"Test requires real API mode, current mode: {api_test_mode}")
         
        # Import processor
        try:
            from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
        except ImportError as e:
            pytest.skip(f"NemoparseProcessor not available: {e}")
         
        # Get endpoint and model from environment
        endpoint_url = os.environ.get('NEMOPARSE_ENDPOINT')
        model_name = os.environ.get('NEMOPARSE_MODEL')
         
        if not endpoint_url or not model_name:
            pytest.skip("Nemoparse endpoint or model not configured")
         
        # Initialize processor with endpoint and model
        processor = NemoparseProcessor(endpoint_url=endpoint_url, model_name=model_name)
         
        # Process actual test file
        sample_pdf = test_data_dir / "docs" / "sample.pdf"
        result = processor.process_document(str(sample_pdf))
        
        # Save output to temporary directory
        result.save_output(str(temp_output_dir), "sample")
        
        # Load saved markdown file
        saved_markdown_path = temp_output_dir / "sample.md"
        assert saved_markdown_path.exists()
        saved_markdown = saved_markdown_path.read_text()
        
        # Load expected markdown output
        expected_markdown_path = test_data_dir / "doc_outputs" / "nemotron" / "sample.md"
        expected_markdown = expected_markdown_path.read_text()
        
        # Compare saved output with expected
        assert saved_markdown == expected_markdown

    def test_process_sample_rotation_pdf_with_auto_detect(self, api_test_mode, temp_output_dir, test_data_dir):
        """Test processing sample_rotation.pdf with auto-rotation detection."""
        # Only run this test when in real API mode
        if api_test_mode != 'real':
            pytest.skip(f"Test requires real API mode, current mode: {api_test_mode}")
         
        # Check if Tesseract is available using existing methods
        try:
            from banyan_extract.utils.rotation_detection import has_tesseract_dependencies
        except ImportError:
            pytest.skip("Rotation detection utilities not available")
         
        if not has_tesseract_dependencies():
            pytest.skip("Tesseract not available for auto-rotation detection")
         
        # Import processor
        try:
            from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
        except ImportError as e:
            pytest.skip(f"NemoparseProcessor not available: {e}")
         
        # Get endpoint and model from environment
        endpoint_url = os.environ.get('NEMOPARSE_ENDPOINT')
        model_name = os.environ.get('NEMOPARSE_MODEL')
         
        if not endpoint_url or not model_name:
            pytest.skip("Nemoparse endpoint or model not configured")
         
        # Initialize processor with endpoint and model
        processor = NemoparseProcessor(endpoint_url=endpoint_url, model_name=model_name)
         
        # Process actual test file with auto-rotation detection
        sample_pdf = test_data_dir / "docs" / "sample_rotation.pdf"
        result = processor.process_document(
            str(sample_pdf),
            auto_detect_rotation=True,
            rotation_confidence_threshold=0.7
        )
        
        # Save output to temporary directory
        result.save_output(str(temp_output_dir), "sample_rotation")
        
        # Load saved markdown file
        saved_markdown_path = temp_output_dir / "sample_rotation.md"
        assert saved_markdown_path.exists()
        saved_markdown = saved_markdown_path.read_text()
        
        # Load expected markdown output
        expected_markdown_path = test_data_dir / "doc_outputs" / "nemotron" / "sample_rotation.pdf.md"
        expected_markdown = expected_markdown_path.read_text()
        
        # Compare saved output with expected
        assert saved_markdown == expected_markdown
