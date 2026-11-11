"""
Unit tests for NemoparseOutput class.

These tests verify the functionality of the NemoparseOutput class
without mocking, using real implementations wherever possible.

Dependency Requirements: nemotronparse dependencies (openai) for full testing
"""

import os
import json
from pathlib import Path
from PIL import Image

import pytest

NemoparseOutput = pytest.importorskip("banyan_extract.output.nemoparse_output").NemoparseOutput
NemoparseData = pytest.importorskip("banyan_extract.output.nemoparse_output").NemoparseData


@pytest.mark.requires_nemotronparse
class TestNemoparseOutputUnit:
    """Unit tests for NemoparseOutput class methods."""

    def test_initialization(self):
        """Test that NemoparseOutput initializes with empty lists."""
        output = NemoparseOutput()
        
        assert output.text == []
        assert output.images == []
        assert output.tables == []
        assert output.bboxdata == []
        assert output.bbox_image == []

    def test_add_output(self):
        """Test adding output data to the NemoparseOutput instance."""
        output = NemoparseOutput()
        
        # Create sample data
        sample_data = NemoparseData(
            text=["Sample text"],
            bbox_json=[{"element": "text", "bbox": [0, 0, 100, 20]}],
            images=[],
            tables=[],
            bbox_image=Image.new('RGB', (100, 100), color='white'),
            page_number=1,
        )
        
        # Add the data
        output.add_output(sample_data)
        
        # Verify the data was added
        assert len(output.text) == 1
        assert len(output.bboxdata) == 1
        assert len(output.bbox_image) == 1
        assert output.text[0] == ["Sample text"]

    def test_get_bbox_output_with_data(self):
        """Test getting bbox output with bbox data included."""
        output = NemoparseOutput()
        
        # Add sample bbox data
        sample_bbox_data = [
            [{"element": "text", "bbox": [0, 0, 100, 20], "content": "Hello"}],
            [{"element": "image", "bbox": [50, 50, 150, 100]}]
        ]
        output.bboxdata = sample_bbox_data
        
        result = output.get_bbox_output(with_bbox_data=True)
        
        # Verify the result contains bbox data
        assert "page_0" in result
        assert "page_1" in result
        assert result["page_0"][0]["bbox"] == [0, 0, 100, 20]

    def test_get_bbox_output_without_data(self):
        """Test getting bbox output without bbox data."""
        output = NemoparseOutput()
        
        # Add sample bbox data
        sample_bbox_data = [
            [{"element": "text", "bbox": [0, 0, 100, 20], "content": "Hello"}],
            [{"element": "image", "bbox": [50, 50, 150, 100]}]
        ]
        output.bboxdata = sample_bbox_data
        
        result = output.get_bbox_output(with_bbox_data=False)
        
        # Verify bbox data is excluded
        assert "page_0" in result
        assert "page_1" in result
        assert "bbox" not in result["page_0"][0]
        assert "content" in result["page_0"][0]

    def test_get_output_as_markdown(self):
        """Test getting output as markdown format."""
        output = NemoparseOutput()
        
        # Add sample text data
        output.text = [
            ["# Heading", "Paragraph text"],
            ["More text"]
        ]
        
        result = output.get_output_as_markdown()
        
        # Verify markdown formatting
        assert "# Heading" in result
        assert "Paragraph text" in result
        assert "More text" in result

    def test_get_content_list(self):
        """Test getting content as a list."""
        output = NemoparseOutput()
        
        # Add sample text data
        output.text = [
            ["First page text"],
            ["Second page text"]
        ]
        
        result = output.get_content_list()
        
        # Verify content list structure
        assert len(result) == 2
        assert result[0] == "First page text"
        assert result[1] == "Second page text"

    def test_get_images(self):
        """Test getting images from output."""
        output = NemoparseOutput()
        
        # Create sample images
        img1 = Image.new('RGB', (100, 100), color='white')
        img2 = Image.new('RGB', (200, 150), color='gray')
        
        output.images = [[img1], [img2]]
        
        result = output.get_images()
        
        # Verify images are returned
        assert len(result) == 2
        assert result[0] == img1
        assert result[1] == img2

    def test_get_output_as_json_without_bboxes(self):
        """The JSON helper should remove bboxes without raising an error."""
        output = NemoparseOutput()
        output.bboxdata = [[{"type": "Text", "text": "Hello", "bbox": {"xmin": 0}}]]

        result = json.loads(output.get_output_as_json(with_bbox_data=False))

        assert result == [[{"type": "Text", "text": "Hello"}]]

    def test_save_output_writes_valid_multi_page_bbox_json(self, tmp_path):
        """BBox artifacts must be one valid JSON document for all pages."""
        output = NemoparseOutput()
        output.text = [["First page"], ["Second page"]]
        output.images = [[], []]
        output.tables = [[], []]
        output.bboxdata = [[{"page": 1}], [{"page": 2}]]
        output.bbox_image = [Image.new("RGB", (1, 1)), Image.new("RGB", (1, 1))]
        output.page_number_list = [1, 2]

        output.save_output(tmp_path, "document", save_bbox_data=True)

        with open(tmp_path / "document_bbox.json", encoding="utf-8") as bbox_file:
            assert json.load(bbox_file) == {"page_0": [{"page": 1}], "page_1": [{"page": 2}]}

    def test_return_bytes_encodes_images(self):
        """Byte-return mode should not expose PIL implementation objects."""
        output = NemoparseOutput()
        output.text = [["Document"]]
        output.images = [[Image.new("RGB", (1, 1), color="white")]]
        output.tables = [[]]
        output.bboxdata = [[]]
        output.bbox_image = [Image.new("RGB", (1, 1), color="white")]
        output.page_number_list = [1]

        result = output.return_bytes("unused", "document", save_images=True, save_bbox_data=True)

        assert result["images"][0].startswith(b"\x89PNG")
        assert result["bbox_images"][0].startswith(b"\x89PNG")


@pytest.mark.requires_nemotronparse
class TestNemoparseOutputEdgeCases:
    """Edge case tests for NemoparseOutput."""

    def test_empty_output(self):
        """Test behavior with empty output."""
        output = NemoparseOutput()
        
        # Test methods with empty data
        assert output.get_bbox_output() == {}
        assert output.get_output_as_markdown() == ""
        assert output.get_content_list() == []
        assert output.get_images() == []

    def test_multiple_pages(self):
        """Test handling of multiple pages of data."""
        output = NemoparseOutput()
        
        # Add data for multiple pages
        for i in range(5):
            sample_data = NemoparseData(
                text=[f"Page {i} text"],
                bbox_json=[{"page": i, "element": "text"}],
                images=[],
                tables=[],
                bbox_image=Image.new('RGB', (100, 100), color='white'),
                page_number=i+1,
            )
            output.add_output(sample_data)
        
        # Verify all pages are stored
        assert len(output.text) == 5
        assert len(output.bboxdata) == 5
        assert len(output.bbox_image) == 5
