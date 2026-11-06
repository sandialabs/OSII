# Test Utilities
# Common utilities and helper functions for tests

import json
import os
from pathlib import Path


def create_sample_pdf(output_path):
    """Create a simple sample PDF file for testing."""
    # This would use a PDF generation library in a real implementation
    # For now, we'll create a minimal placeholder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write("%PDF-1.4\n%")  # Minimal PDF header


def create_sample_pptx(output_path):
    """Create a simple sample PPTX file for testing."""
    # This would use python-pptx in a real implementation
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write("PK\x03\x04")  # Minimal PPTX header


def create_sample_json_output(output_path, data=None):
    """Create a sample JSON output file."""
    if data is None:
        data = {
            "pages": [
                {
                    "page_number": 1,
                    "elements": [
                        {
                            "type": "text",
                            "content": "Sample text",
                            "position": {"x": 10, "y": 20, "width": 100, "height": 20}
                        }
                    ]
                }
            ]
        }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def compare_json_files(file1, file2):
    """Compare two JSON files for testing purposes."""
    with open(file1) as f1, open(file2) as f2:
        data1 = json.load(f1)
        data2 = json.load(f2)
        return data1 == data2


def setup_test_data_directory(data_dir):
    """Set up a complete test data directory structure."""
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create processor test data
    processor_dir = data_dir / "processors"
    processor_dir.mkdir(exist_ok=True)
    create_sample_pdf(processor_dir / "sample.pdf")
    create_sample_pptx(processor_dir / "sample.pptx")
    
    # Create output test data
    output_dir = data_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    create_sample_json_output(output_dir / "sample_output.json")
    
    # Create converter test data
    converter_dir = data_dir / "converters"
    converter_dir.mkdir(exist_ok=True)
    create_sample_pdf(converter_dir / "input.pdf")


if __name__ == "__main__":
    # Set up test data when this module is run directly
    test_data_dir = Path(__file__).parent / "data"
    setup_test_data_directory(test_data_dir)
    # Removed print statement to reduce verbosity