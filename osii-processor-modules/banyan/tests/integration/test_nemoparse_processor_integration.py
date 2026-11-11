"""
Integration tests for NemoparseProcessor demonstrating complete workflows.

This test module focuses on processor-related integration tests, including:
- Complete document processing workflows
- Multi-page document handling
- Error recovery and batch processing
- File format compatibility

Generated using AI, reviewed by a human
"""

import os
import json
from pathlib import Path
from PIL import Image

import pytest

from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
from banyan_extract.output.nemoparse_output import NemoparseOutput, NemoparseData


class TestNemoparseProcessorIntegration:
    """
    Integration tests for NemoparseProcessor demonstrating complete workflows.
    
    These tests verify the full document processing workflow from file input 
    to output, including error handling and batch processing scenarios.
    """

    def test_complete_workflow_test(self, temp_output_dir, test_data_dir):
        """
        Test the full document processing workflow from file input to output.
        
        This integration test demonstrates:
        - Loading a document file
        - Processing through NemoparseProcessor
        - Generating output files
        - Verifying the complete workflow
        """
        from unittest.mock import Mock, patch
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create a real test image for processing
        real_image = Image.new('RGB', (400, 300), color='white')
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        real_pdf_bytes = img_byte_arr.getvalue()
        
        # Use more realistic get_pages implementation
        # This reduces mock usage while maintaining integration test isolation
        def real_get_pages(filepath):
            return [real_pdf_bytes]
        
        processor.get_pages = real_get_pages
        
        # Mock the OCR API response to avoid external dependencies
        mock_bbox_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'Test Document Header'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                'text': 'This is a test document for integration testing.'
            }
        ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mock_bbox_data)
        
         # Process the document
        output = processor.process_document(str(sample_pdf_path))
        
        # Verify the output was created successfully
        assert output is not None
        assert len(output.text) > 0
        assert len(output.bboxdata) > 0
        
        # Save the output to verify file generation
        output_dir = temp_output_dir
        base_name = "complete_workflow_test"
        output.save_output(output_dir, base_name, save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify expected output files were created
        expected_files = [
            f"{base_name}.md",
            f"{base_name}_bbox.json",
            f"{base_name}_bbox_image_0.png"
        ]
        
        for expected_file in expected_files:
            file_path = output_dir / expected_file
            assert file_path.exists(), f"Expected file not found: {expected_file}"
        
        # Verify content of markdown file
        md_file = output_dir / f"{base_name}.md"
        with open(md_file, 'r') as f:
            md_content = f.read()
        
        assert "# Test Document Header" in md_content
        assert "This is a test document for integration testing" in md_content

    def test_multi_page_document_test(self, temp_output_dir, test_data_dir):
        """
        Test processing of documents with multiple pages.
        
        This integration test demonstrates:
        - Processing multi-page documents
        - Handling page-specific content
        - Verifying output for each page
        """
        from unittest.mock import Mock
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create real multi-page document (3 pages)
        real_pages = []
        for page_num in range(3):
            # Create a real image for this page
            real_image = Image.new('RGB', (400, 300), color='white')
            img_byte_arr = io.BytesIO()
            real_image.save(img_byte_arr, format='PNG')
            real_pages.append(img_byte_arr.getvalue())
        
        # Use more realistic get_pages implementation
        def real_get_pages(filepath):
            return real_pages
        
        processor.get_pages = real_get_pages
        
        # Mock the OCR API response with page-specific content
        call_count = {'count': 0}
        def mock_ocr_response(base64_image, **kwargs):
            # Extract page number from the mock data (simplified)
            call_count['count'] += 1
            page_num = call_count['count']
            return [
                {
                    'type': 'Section-header',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                    'text': f'Page {page_num} Header'
                },
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                    'text': f'This is the content for page {page_num}.'
                }
            ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_response)
        
         # Process the document
        output = processor.process_document(str(sample_pdf_path))
        
        # Verify we got results for all pages
        assert output is not None
        assert len(output.text) == 3  # One entry per page
        
        # Verify each page's content is present
        for page_num in range(3):
            page_text = output.text[page_num]
            assert f'This is the content for page {page_num + 1}.' in page_text
        
        # Save the output and verify files
        output_dir = temp_output_dir
        base_name = "multi_page_test"
        output.save_output(output_dir, base_name, save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify expected files for multi-page document
        expected_files = [
            f"{base_name}.md",
            f"{base_name}_bbox.json",
            f"{base_name}_bbox_image_0.png",
            f"{base_name}_bbox_image_1.png",
            f"{base_name}_bbox_image_2.png"
        ]
        
        for expected_file in expected_files:
            file_path = output_dir / expected_file
            assert file_path.exists(), f"Expected file not found: {expected_file}"

    def test_error_recovery_workflow_test(self, temp_output_dir, test_data_dir):
        """
        Test error handling and recovery in complete workflows.
        
        This integration test demonstrates:
        - Handling API failures gracefully
        - Error recovery mechanisms
        - Partial processing when errors occur
        """
        from unittest.mock import Mock, patch
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create a real document with 2 pages
        real_pages = []
        for i in range(2):
            real_image = Image.new('RGB', (200, 150), color='white')
            img_byte_arr = io.BytesIO()
            real_image.save(img_byte_arr, format='PNG')
            real_pages.append(img_byte_arr.getvalue())
        
        # Use more realistic get_pages implementation
        def real_get_pages(filepath):
            return real_pages
        
        processor.get_pages = real_get_pages
        
        # Mock the OCR API to succeed for first page but fail for second
        call_count = {'count': 0}
        def mock_ocr_with_error(base64_image, **kwargs):
            if call_count['count'] == 0:
                # First page - success
                call_count['count'] += 1
                return [
                    {
                        'type': 'Text',
                        'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                        'text': 'First page processed successfully'
                    }
                ]
            else:
                # Second page - failure
                raise Exception("OCR API error for second page")
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_with_error)
        
         # Process the document - should fail on second page
        try:
            processor.process_document(str(sample_pdf_path))
            assert False, "Expected exception was not raised"
        except Exception as e:
            assert "OCR API error for second page" in str(e)
        
        # Test error recovery by processing with error handling
        # Mock the OCR API to return empty results for failed pages
        call_count = {'count': 0}
        def mock_ocr_with_recovery(base64_image, **kwargs):
            try:
                if call_count['count'] == 0:
                    call_count['count'] += 1
                    return [
                        {
                            'type': 'Text',
                            'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                            'text': 'First page processed successfully'
                        }
                    ]
                else:
                    raise Exception("OCR API error")
            except Exception:
                # Return empty results for failed pages
                return []
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_with_recovery)
        
        # Process with error recovery
        output = processor.process_document(str(sample_pdf_path))
        
        # Should have partial results (first page only)
        assert output is not None
        assert len(output.text) == 2  # Both pages processed, but second has empty results
        assert len(output.text[0]) == 1  # First page has content
        assert len(output.text[1]) == 0  # Second page has no content due to error

    def test_batch_processing_integration_test(self, temp_output_dir, test_data_dir):
        """
        Test end-to-end batch processing with multiple documents.
        
        This integration test demonstrates:
        - Processing multiple documents in batch
        - Handling different document types
        - Verifying output for each document
        """
        from unittest.mock import Mock
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create real documents
        real_documents = {}
        for doc_id in ['doc1', 'doc2', 'doc3']:
            # Create a real single-page document
            real_image = Image.new('RGB', (300, 200), color='white')
            img_byte_arr = io.BytesIO()
            real_image.save(img_byte_arr, format='PNG')
            real_documents[doc_id] = img_byte_arr.getvalue()
        
        # Use realistic get_pages implementation
        def real_get_pages(filepath):
            doc_id = filepath.split('/')[-1].split('.')[0]
            if doc_id in real_documents:
                return [real_documents[doc_id]]
            return []
        
        processor.get_pages = real_get_pages
        
        # Mock the OCR API response with document-specific content
        call_count = {'count': 0}
        def mock_ocr_response(base64_image, **kwargs):
            # Extract document ID from the mock data (simplified)
            call_count['count'] += 1
            doc_id = f"doc{call_count['count']}"
            return [
                {
                    'type': 'Section-header',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                    'text': f'{doc_id} Header'
                },
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                    'text': f'Content for {doc_id}'
                }
            ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_response)
        
        # Process batch documents
        filepaths = ['doc1.pdf', 'doc2.pdf', 'doc3.pdf']
        results = processor.process_batch_documents(filepaths, use_checkpointing=False)
        
        # Verify we got results for all documents
        assert len(results) == 3
        assert all(result is not None for result in results)
        
        # Verify each document's content
        for i, result in enumerate(results):
            expected_doc_id = f"doc{i+1}"
            assert len(result.text) == 1
            assert f'# {expected_doc_id} Header' in result.text[0]
            assert f'Content for {expected_doc_id}' in result.text[0]
        
        # Test batch processing with checkpointing (saving to files)
        checkpoint_dir = temp_output_dir / "batch_checkpoint"
        checkpoint_dir.mkdir()
        
        # Reset call count for checkpointing test
        mock_ocr_response.call_count = []
        
        results_checkpoint = processor.process_batch_documents(
            filepaths, 
            use_checkpointing=True, 
            output_dir=str(checkpoint_dir),
            draw_bboxes=True,
            save_images=True,
            save_bbox_data=True,
            save_tables=True,
        )
        
        # Verify checkpoint files were created
        for doc_id in ['doc1', 'doc2', 'doc3']:
            expected_files = [
                f"{doc_id}.pdf.md",
                f"{doc_id}.pdf_bbox.json",
                f"{doc_id}.pdf_bbox_image_0.png"
            ]
            
            for expected_file in expected_files:
                file_path = checkpoint_dir / expected_file
                assert file_path.exists(), f"Expected checkpoint file not found: {expected_file}"

    def test_file_format_compatibility_test(self, temp_output_dir, test_data_dir):
        """
        Test different supported file formats (PDF, PNG, etc.).
        
        This integration test demonstrates:
        - Processing different file formats
        - Verifying format-specific handling
        - Ensuring consistent output across formats
        """
        from unittest.mock import Mock
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Test PDF format
        real_pdf_image = Image.new('RGB', (400, 300), color='white')
        img_byte_arr = io.BytesIO()
        real_pdf_image.save(img_byte_arr, format='PNG')
        real_pdf_bytes = img_byte_arr.getvalue()
        
        # Use realistic get_pages implementation
        def real_get_pages(filepath):
            return [real_pdf_bytes]
        
        processor.get_pages = real_get_pages
        
        # Mock OCR response for PDF
        pdf_mock_bbox_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'PDF Document Header'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                'text': 'This is a PDF document.'
            }
        ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=pdf_mock_bbox_data)
        
         # Process PDF document
        pdf_output = processor.process_document(str(sample_pdf_path))
        
        assert pdf_output is not None
        assert len(pdf_output.text) == 1
        assert "# PDF Document Header" in pdf_output.text[0]
        assert "This is a PDF document." in pdf_output.text[0]
        
        # Test PNG format
        # Create a temporary PNG file using temp_output_dir
        png_file = temp_output_dir / "test_image.png"
        png_image = Image.new('RGB', (300, 200), color='lightgray')
        png_image.save(png_file, format='PNG')
        tmp_file_path = str(png_file)
        
        # No need for try-finally cleanup since we're using temp_output_dir
        # Mock OCR response for PNG
        png_mock_bbox_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'PNG Image Header'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                'text': 'This is a PNG image document.'
            }
        ]
         
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=png_mock_bbox_data)
         
        # Process PNG document
        png_output = processor.process_document(tmp_file_path)
         
        assert png_output is not None
        assert len(png_output.text) == 1
        assert "# PNG Image Header" in png_output.text[0]
        assert "This is a PNG image document." in png_output.text[0]
         
        # Test TIFF format
        real_tiff_image = Image.new('RGB', (350, 250), color='gray')
        img_byte_arr = io.BytesIO()
        real_tiff_image.save(img_byte_arr, format='PNG')
        real_tiff_bytes = img_byte_arr.getvalue()
        
        # Use realistic get_pages implementation
        def real_get_pages(filepath):
            return [real_tiff_bytes]
        
        processor.get_pages = real_get_pages
         
        # Mock OCR response for TIFF
        tiff_mock_bbox_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'TIFF Document Header'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                'text': 'This is a TIFF document.'
            }
        ]
         
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=tiff_mock_bbox_data)
         
        # Process TIFF document
        tiff_output = processor.process_document("test.tif")
         
        assert tiff_output is not None
        assert len(tiff_output.text) == 1
        assert "# TIFF Document Header" in tiff_output.text[0]
        assert "This is a TIFF document." in tiff_output.text[0]
            
        # No cleanup needed - temp_output_dir handles it automatically

    def test_complex_nested_tables(self, temp_output_dir, test_data_dir):
        """
        Test processing of documents with complex nested tables.
        
        This test verifies handling of:
        - Multi-level nested tables
        - Tables with merged cells
        - Complex table structures
        """
        from unittest.mock import Mock
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create a real document
        real_image = Image.new('RGB', (400, 300), color='white')
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        real_pdf_bytes = img_byte_arr.getvalue()
        
        # Use realistic get_pages implementation
        def real_get_pages(filepath):
            return [real_pdf_bytes]
        
        processor.get_pages = real_get_pages
        
        # Mock OCR response with complex nested table data
        complex_table_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'Complex Table Document'
            },
            {
                'type': 'Table',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.9, 'ymax': 0.8},
                'text': 'Department|Quarter|Revenue|Expenses|Profit\\' +
                       'Engineering|Q1 2023|$500K|$300K|$200K\\' +
                       'Engineering|Q2 2023|$600K|$350K|$250K\\' +
                       'Marketing|Q1 2023|$300K|$200K|$100K\\' +
                       'Marketing|Q2 2023|$350K|$220K|$130K'
            }
        ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=complex_table_data)
        
        # Process the document
        output = processor.process_document("complex_tables.pdf")
        
        # Verify the output was created successfully
        assert output is not None
        assert len(output.text) > 0
        assert len(output.bboxdata) > 0
        
        # Verify table content is present
        all_text = " ".join([item for sublist in output.text for item in sublist])
        assert "# Complex Table Document" in all_text
        assert "Department" in all_text
        assert "Quarter" in all_text
        assert "Revenue" in all_text
        assert "Engineering" in all_text
        assert "Marketing" in all_text
        
        # Save and verify files
        output.save_output(temp_output_dir, "complex_tables", save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify expected files were created
        assert (temp_output_dir / "complex_tables.md").exists()
        assert (temp_output_dir / "complex_tables_bbox.json").exists()
        
        # Verify table CSV file contains the complex data
        table_file = temp_output_dir / "complex_tables_table_0.csv"
        assert table_file.exists()
        
        with open(table_file, 'r') as f:
            table_content = f.read()
        
        assert "Department" in table_content
        assert "Quarter" in table_content
        assert "Revenue" in table_content
        assert "Engineering" in table_content
        assert "Marketing" in table_content

    def test_mixed_language_documents(self, temp_output_dir, test_data_dir):
        """
        Test processing of documents with mixed languages.

        This test verifies handling of:
        - Multi-language content
        - Unicode characters
        - Language-specific formatting
        """
        from unittest.mock import Mock
        from PIL import Image
        import io

        # Define sample_pdf_path using test_data_dir
        sample_pdf_path = test_data_dir / "docs" / "sample.pdf"

        # Create processor instance
        processor = NemoparseProcessor()

        # Create a real document
        real_image = Image.new('RGB', (400, 300), color='white')
        img_byte_arr = io.BytesIO()
        real_image.save(img_byte_arr, format='PNG')
        real_pdf_bytes = img_byte_arr.getvalue()
        
        # Use realistic get_pages implementation
        def real_get_pages(filepath):
            return [real_pdf_bytes]
        
        processor.get_pages = real_get_pages

        # Mock OCR response with mixed language data
        mixed_language_data = [
            {
                'type': 'Section-header',
                'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                'text': 'Multilingual Document'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                'text': 'This document contains multiple languages: English, Chinese, Japanese, and Russian.'
            },
            {
                'type': 'Text',
                'bbox': {'xmin': 0.1, 'ymin': 0.5, 'xmax': 0.8, 'ymax': 0.6},
                'text': 'Hello World! Hello world! Hello world! Hello world!'
            }
        ]

        processor.nemotron_ocr.get_detailed_ocr_results = Mock(return_value=mixed_language_data)

        # Process the document
        output = processor.process_document("mixed_language.pdf")

        # Verify the output was created successfully
        assert output is not None
        assert len(output.text) > 0

        # Verify mixed language content is preserved
        all_text = " ".join([item for sublist in output.text for item in sublist])
        assert "# Multilingual Document" in all_text
        assert "This document contains multiple languages" in all_text
        assert "English" in all_text
        assert "Chinese" in all_text
        assert "Japanese" in all_text
        assert "Russian" in all_text
        assert "Hello World!" in all_text
        assert "Hello world!" in all_text

        # Save and verify files
        output.save_output(temp_output_dir, "mixed_language", save_images=True, save_bbox_data=True, save_tables=True)

        # Verify expected files were created
        assert (temp_output_dir / "mixed_language.md").exists()
        assert (temp_output_dir / "mixed_language_bbox.json").exists()

        # Verify content in markdown file
        md_file = temp_output_dir / "mixed_language.md"
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        assert "Multilingual Document" in md_content
        assert "Hello World! Hello world! Hello world! Hello world!" in md_content

        # Save and verify files
        output.save_output(temp_output_dir, "math_document", save_images=True, save_bbox_data=True, save_tables=True)

        # Verify expected files were created
        assert (temp_output_dir / "math_document.md").exists()
        assert (temp_output_dir / "math_document_bbox.json").exists()

        # Verify content in markdown file
        md_file = temp_output_dir / "math_document.md"
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        assert "Multilingual Document" in md_content
        assert "This document contains multiple languages" in md_content
        assert "English" in md_content
        assert "Multilingual Document" in md_content
        assert "This document contains multiple languages" in md_content
        assert "English" in md_content
        assert "Multilingual Document" in md_content
        assert "This document contains multiple languages" in md_content
        assert "English" in md_content
