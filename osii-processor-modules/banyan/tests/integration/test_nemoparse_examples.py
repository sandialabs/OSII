"""
Example-based tests for NemoparseOutput and NemoparseProcessor.

This test module contains example-based tests that serve as user documentation.
These tests demonstrate real-world usage patterns and can be used as templates.

Generated using AI, reviewed by a human
"""

import os
import json
from pathlib import Path
from PIL import Image

import pytest

from banyan_extract.output.nemoparse_output import NemoparseOutput, NemoparseData


class TestNemoparseOutputExampleBased:
    """
    Example-based tests that serve as user documentation.
    
    These tests demonstrate real-world usage patterns
    and can be used as templates for users.
    """

    def test_basic_usage_example(self, temp_output_dir):
        """
        Example: Basic usage of NemoparseOutput
        
        This example shows the simplest way to use NemoparseOutput:
        1. Create an instance
        2. Add processed data
        3. Save the output
        
        Users can adapt this example for their own document processing needs.
        """
        # Step 1: Create NemoparseOutput instance
        document_output = NemoparseOutput()
        
        # Step 2: Process a document (simulated here)
        # In real usage, this would come from a processor
        page_data = NemoparseData(
            text=["# Sample Document", "This is a sample document for testing."],
            bbox_json=[
                {
                    "type": "heading",
                    "bbox": [20, 20, 200, 40],
                    "text": "Sample Document",
                    "confidence": 0.97
                }
            ],
            images=[Image.new('RGB', (100, 100), color='white')],
            tables=[],
            bbox_image=Image.new('RGB', (100, 100), color='white'),
            page_number=1,
        )
        
        document_output.add_output(page_data)
        
        # Step 3: Save the output
        output_path = temp_output_dir
        document_output.save_output(output_path, "sample_document", save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify the output was saved correctly
        assert (temp_output_dir / "sample_document.md").exists()
        assert (temp_output_dir / "sample_document_bbox.json").exists()
        
        # Show the user how to access the output data programmatically
        markdown_content = document_output.get_output_as_markdown()
        assert "# Sample Document" in markdown_content
        
        bbox_data = document_output.get_bbox_output()
        assert "page_0" in bbox_data

    def test_multi_page_document_example(self, temp_output_dir):
        """
        Example: Processing a multi-page document
        
        This example demonstrates how to handle documents with multiple pages:
        - Adding data for each page sequentially
        - Accessing page-specific content
        - Working with the complete document output
        """
        # Create output for a multi-page document
        doc_output = NemoparseOutput()
        
        # Process multiple pages
        for page_num in range(1, 4):  # 3 pages
            page_data = NemoparseData(
                text=[f"# Page {page_num + 1}", f"Content for page {page_num + 1}"],
                bbox_json=[
                    {
                        "type": "heading",
                        "bbox": [20, 20, 150, 40],
                        "text": f"Page {page_num + 1}",
                        "confidence": 0.95 + (page_num * 0.01)
                    }
                ],
                images=[Image.new('RGB', (200, 150), color='lightgray')],
                tables=[f"Page|Content\{page_num}|Sample content"],
                bbox_image=Image.new('RGB', (200, 150), color='white'),
                page_number=page_num,
            )
            doc_output.add_output(page_data)
        
        # Save the complete document
        doc_output.save_output(temp_output_dir, "multi_page_doc", save_images=True, save_bbox_data=True, save_tables=True)
        
        # Demonstrate accessing page-specific content
        content_list = doc_output.get_content_list()
        assert len(content_list) == 3
        # The content list concatenates all text for each page
        assert "Page 1" in content_list[0] or "Page 2" in content_list[0] or "Page 3" in content_list[0]
        assert "Content for page" in str(content_list)
        
        # Show how to get all images from the document
        all_images = doc_output.get_images()
        assert len(all_images) == 3  # One image per page
        
        # Verify all expected files were created
        expected_files = [
            "multi_page_doc.md",
            "multi_page_doc_bbox.json",
            "multi_page_doc_bbox_image_0.png",
            "multi_page_doc_bbox_image_1.png",
            "multi_page_doc_bbox_image_2.png",
            "multi_page_doc_image_0.png",
            "multi_page_doc_image_1.png",
            "multi_page_doc_image_2.png",
            "multi_page_doc_table_0.csv",
            "multi_page_doc_table_1.csv",
            "multi_page_doc_table_2.csv"
        ]
        
        for expected_file in expected_files:
            assert (temp_output_dir / expected_file).exists()

    def test_complex_document_structure_example(self, temp_output_dir):
        """
        Example: Processing a document with complex structure
        
        This example demonstrates handling of:
        - Documents with headings, paragraphs, and tables
        - Multiple element types per page
        - Complex bbox data structures
        """
        # Create output for a complex document
        complex_output = NemoparseOutput()
        
        # Add a page with complex structure
        complex_page_data = NemoparseData(
            text=[
                "# Annual Report 2023",
                "## Financial Summary",
                "The company achieved record revenue in 2023.",
                "## Key Metrics",
                "- Revenue growth: 25%",
                "- Customer satisfaction: 95%",
                "- Market share: 15%"
            ],
            bbox_json=[
                {
                    "type": "title",
                    "bbox": [50, 50, 400, 80],
                    "text": "Annual Report 2023",
                    "confidence": 0.98
                },
                {
                    "type": "heading",
                    "bbox": [50, 100, 300, 130],
                    "text": "Financial Summary",
                    "confidence": 0.96
                },
                {
                    "type": "paragraph",
                    "bbox": [50, 150, 500, 200],
                    "text": "The company achieved record revenue in 2023.",
                    "confidence": 0.94
                },
                {
                    "type": "heading",
                    "bbox": [50, 220, 250, 250],
                    "text": "Key Metrics",
                    "confidence": 0.95
                },
                {
                    "type": "list",
                    "bbox": [50, 260, 450, 350],
                    "text": "- Revenue growth: 25%\\- Customer satisfaction: 95%\\- Market share: 15%",
                    "confidence": 0.93
                }
            ],
            images=[
                Image.new('RGB', (600, 400), color='white'),  # Main chart
                Image.new('RGB', (300, 200), color='lightgray')  # Secondary chart
            ],
            tables=[
                "Quarter|Revenue|Profit\\Q1|$1.2M|$300K\\Q2|$1.5M|$400K\\Q3|$1.8M|$500K\\Q4|$2.1M|$600K"
            ],
            bbox_image=Image.new('RGB', (600, 400), color='white'),
            page_number=1,
        )
        
        complex_output.add_output(complex_page_data)
        
        # Save the complex document
        complex_output.save_output(temp_output_dir, "complex_report", save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify the output
        assert (temp_output_dir / "complex_report.md").exists()
        assert (temp_output_dir / "complex_report_bbox.json").exists()
        assert (temp_output_dir / "complex_report_image_0.png").exists()
        assert (temp_output_dir / "complex_report_image_1.png").exists()
        assert (temp_output_dir / "complex_report_table_0.csv").exists()
        
        # Verify content
        with open(temp_output_dir / "complex_report.md", 'r') as f:
            content = f.read()
        
        assert "# Annual Report 2023" in content
        assert "## Financial Summary" in content
        assert "## Key Metrics" in content
        assert "The company achieved record revenue" in content
        assert "Revenue growth: 25%" in content

    def test_batch_processing_example(self, temp_output_dir, test_data_dir):
        """
        Example: Batch processing multiple documents
        
        This example demonstrates:
        - Processing multiple documents in a batch
        - Organizing output for each document
        - Handling different document types
        """
        from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
        from unittest.mock import Mock
        from PIL import Image
        import io
        
        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create mock documents for batch processing
        mock_documents = {}
        document_names = ['invoice_001', 'contract_001', 'report_001']
        
        for doc_name in document_names:
            # Create a mock single-page document
            mock_image = Image.new('RGB', (300, 200), color='white')
            img_byte_arr = io.BytesIO()
            mock_image.save(img_byte_arr, format='PNG')
            mock_documents[doc_name] = img_byte_arr.getvalue()
        
        # Mock the get_pages method
        def mock_get_pages(filepath):
            doc_name = filepath.split('/')[-1].split('.')[0]
            if doc_name in mock_documents:
                return [mock_documents[doc_name]]
            return []
        
        processor.get_pages = Mock(side_effect=mock_get_pages)
        
        # Mock the OCR API response with document-specific content
        call_count = {'count': 0}
        def mock_ocr_response(base64_image, **kwargs):
            call_count['count'] += 1
            doc_name = document_names[call_count['count'] - 1]
            return [
                {
                    'type': 'Section-header',
                    'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.9, 'ymax': 0.2},
                    'text': f'{doc_name.replace("_", " ").title()}'
                },
                {
                    'type': 'Text',
                    'bbox': {'xmin': 0.1, 'ymin': 0.3, 'xmax': 0.8, 'ymax': 0.4},
                    'text': f'This is the content for {doc_name}.'
                }
            ]
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_response)
        
        # Process batch documents
        filepaths = [str(test_data_dir / "docs" / f"{name}.pdf") for name in document_names]
        results = processor.process_batch_documents(filepaths, use_checkpointing=False)
        
        # Verify we got results for all documents
        assert len(results) == 3
        assert all(result is not None for result in results)
        
        # Save each document's output
        for i, result in enumerate(results):
            doc_name = document_names[i]
            result.save_output(temp_output_dir, doc_name, save_images=True, save_bbox_data=True, save_tables=True)
            
            # Verify files were created for this document
            assert (temp_output_dir / f"{doc_name}.md").exists()
            assert (temp_output_dir / f"{doc_name}_bbox.json").exists()

    def test_error_handling_example(self, temp_output_dir):
        """
        Example: Error handling in document processing
        
        This example demonstrates:
        - Handling errors gracefully
        - Providing meaningful error messages
        - Recovering from partial failures
        """
        from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
        from unittest.mock import Mock
        from PIL import Image
        import io
        
        # Create processor instance
        processor = NemoparseProcessor()
        
        # Create a mock document
        mock_image = Image.new('RGB', (200, 150), color='white')
        img_byte_arr = io.BytesIO()
        mock_image.save(img_byte_arr, format='PNG')
        mock_pdf_bytes = img_byte_arr.getvalue()
        
        processor.get_pages = Mock(return_value=[mock_pdf_bytes])
        
        # Mock the OCR API to fail
        def mock_ocr_failure(base64_image, **kwargs):
            raise Exception("OCR service temporarily unavailable")
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_failure)
        
        # Try to process the document - should fail gracefully
        try:
            processor.process_document("error_test.pdf")
            assert False, "Expected exception was not raised"
        except Exception as e:
            # Verify we get a meaningful error message
            assert "OCR service temporarily unavailable" in str(e)
            print(f"Error handled gracefully: {e}")
        
        # Example: Processing with error recovery
        def mock_ocr_with_recovery(base64_image, **kwargs):
            try:
                # Simulate OCR that might fail
                return [
                    {
                        'type': 'Text',
                        'bbox': {'xmin': 0.1, 'ymin': 0.1, 'xmax': 0.5, 'ymax': 0.2},
                        'text': 'Successfully processed content'
                    }
                ]
            except Exception:
                # Return empty results on failure
                return []
        
        processor.nemotron_ocr.get_detailed_ocr_results = Mock(side_effect=mock_ocr_with_recovery)
        
        # Process with error recovery
        output = processor.process_document("recovery_test.pdf")
        
        # Should have results (even if partial)
        assert output is not None
        print("Document processed with error recovery")

    def test_custom_output_formatting_example(self, temp_output_dir):
        """
        Example: Custom output formatting
        
        This example demonstrates:
        - Accessing raw output data
        - Custom formatting options
        - Creating specialized output formats
        """
        # Create output instance
        custom_output = NemoparseOutput()
        
        # Add sample data
        sample_data = NemoparseData(
            text=[
                "# Research Paper",
                "## Abstract",
                "This paper presents our findings on document processing.",
                "## Introduction",
                "Document processing is a complex field with many challenges."
            ],
            bbox_json=[
                {
                    "type": "title",
                    "bbox": [50, 50, 300, 80],
                    "text": "Research Paper",
                    "confidence": 0.98
                },
                {
                    "type": "heading",
                    "bbox": [50, 100, 200, 130],
                    "text": "Abstract",
                    "confidence": 0.96
                }
            ],
            images=[Image.new('RGB', (400, 300), color='white')],
            tables=["Section|Word Count\\Abstract|50\\Introduction|100"],
            bbox_image=Image.new('RGB', (400, 300), color='white'),
            page_number=1,
        )
        
        custom_output.add_output(sample_data)
        
        # Example 1: Get raw markdown content
        markdown_content = custom_output.get_output_as_markdown()
        print("Markdown content:")
        print(markdown_content)
        
        # Example 2: Get bbox data as JSON
        bbox_json = custom_output.get_bbox_output()
        print("BBox JSON:")
        print(json.dumps(bbox_json, indent=2))
        
        # Example 3: Get content list for custom processing
        content_list = custom_output.get_content_list()
        print("Content list:")
        for i, content in enumerate(content_list):
            print(f"Page {i+1}: {content[:100]}...")
        
        # Example 4: Get images for custom processing
        images = custom_output.get_images()
        print(f"Retrieved {len(images)} images")
        
        # Example 5: Custom formatting - extract headings only
        all_text = custom_output.get_output_as_markdown()
        headings = [line for line in all_text.split('\n') if line.startswith('#')]
        print("Headings found:")
        for heading in headings:
            print(f"  {heading}")
        
        # Save with standard formatting
        custom_output.save_output(temp_output_dir, "custom_formatted", save_images=True, save_bbox_data=True, save_tables=True)
        
        # Verify all files were created
        assert (temp_output_dir / "custom_formatted.md").exists()
        assert (temp_output_dir / "custom_formatted_bbox.json").exists()
        assert (temp_output_dir / "custom_formatted_image_0.png").exists()
        assert (temp_output_dir / "custom_formatted_table_0.csv").exists()
