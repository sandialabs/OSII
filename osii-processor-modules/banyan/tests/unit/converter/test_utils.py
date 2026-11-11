import pytest
from banyan_extract.converter.utils import file_requires_conversion

def test_file_requires_conversion_docx():
    assert file_requires_conversion("test.docx") is True

def test_file_requires_conversion_pdf():
    assert file_requires_conversion("test.pdf") is False

def test_file_requires_conversion_unknown():
    assert file_requires_conversion("test.txt") is False
