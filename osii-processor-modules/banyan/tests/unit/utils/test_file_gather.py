import pytest
from pathlib import Path
from banyan_extract.utils.file_gather import gather_files

@pytest.fixture
def test_dir(tmp_path):
    """Create a dummy directory structure for testing."""
    # Root
    (tmp_path / "file1.pdf").write_text("content")
    (tmp_path / "slides.pptx").write_text("content")
    (tmp_path / "readme.txt").write_text("content")
    (tmp_path / ".hidden_file.pdf").write_text("content")
    
    # Subdir 1 (Depth 1)
    subdir1 = tmp_path / "subdir1"
    subdir1.mkdir()
    (subdir1 / "file2.pdf").write_text("content")
    (subdir1 / "file3.pdf").write_text("content")
    (subdir1 / "image.png").write_text("content")
    (subdir1 / ".hidden_subdir").mkdir()
    (subdir1 / ".hidden_subdir" / "hidden.pdf").write_text("content")
    
    # Subdir 2 (Depth 1)
    subdir2 = tmp_path / "subdir2"
    subdir2.mkdir()
    (subdir2 / "image2.png").write_text("content")
    
    # Subdir 2/Subdir 3 (Depth 2)
    subdir3 = subdir2 / "subdir3"
    subdir3.mkdir()
    (subdir3 / "file4.pdf").write_text("content")
    
    # Subdir 2/Subdir 4 (Depth 2)
    subdir4 = subdir2 / "subdir4"
    subdir4.mkdir()
    (subdir4 / "file5.pdf").write_text("content")
    
    return tmp_path

def test_gather_files_pdf_depth_1(test_dir):
    """Verify gathering PDF files with max_depth=1 (default)."""
    extensions = {"pdf"}
    result = gather_files(test_dir, extensions, max_depth=1)
    
    expected = {
        Path("file1.pdf"),
        Path("subdir1/file2.pdf"),
        Path("subdir1/file3.pdf"),
    }
    assert set(result) == expected

def test_gather_files_pdf_depth_2(test_dir):
    """Verify gathering PDF files with max_depth=2."""
    extensions = {"pdf"}
    result = gather_files(test_dir, extensions, max_depth=2)
    
    expected = {
        Path("file1.pdf"),
        Path("subdir1/file2.pdf"),
        Path("subdir1/file3.pdf"),
        Path("subdir2/subdir3/file4.pdf"),
        Path("subdir2/subdir4/file5.pdf"),
    }
    assert set(result) == expected

def test_gather_files_pdf_infinite_depth(test_dir):
    """Verify gathering PDF files with max_depth=-1."""
    extensions = {"pdf"}
    result = gather_files(test_dir, extensions, max_depth=-1)
    
    expected = {
        Path("file1.pdf"),
        Path("subdir1/file2.pdf"),
        Path("subdir1/file3.pdf"),
        Path("subdir2/subdir3/file4.pdf"),
        Path("subdir2/subdir4/file5.pdf"),
    }
    assert set(result) == expected

def test_gather_files_ignore_hidden(test_dir):
    """Verify that hidden files and directories are ignored."""
    extensions = {"pdf"}
    result = gather_files(test_dir, extensions, max_depth=-1)
    
    # .hidden_file.pdf and .hidden_subdir/hidden.pdf should be missing
    for p in result:
        assert not p.name.startswith(".")
        assert not any(part.startswith(".") for part in p.parts)

def test_gather_files_pdf_pptx(test_dir):
    """Verify gathering PDF and PPTX files."""
    extensions = {"pdf", "pptx"}
    result = gather_files(test_dir, extensions, max_depth=-1)
    
    expected = {
        Path("file1.pdf"),
        Path("slides.pptx"),
        Path("subdir1/file2.pdf"),
        Path("subdir1/file3.pdf"),
        Path("subdir2/subdir3/file4.pdf"),
        Path("subdir2/subdir4/file5.pdf"),
    }
    assert set(result) == expected

def test_gather_files_custom_extension(test_dir):
    """Verify gathering files with a custom extension."""
    extensions = {"txt"}
    result = gather_files(test_dir, extensions, max_depth=-1)
    
    expected = {Path("readme.txt")}
    assert set(result) == expected

def test_gather_files_no_match(test_dir):
    """Verify result is empty when no extensions match."""
    extensions = {"docx"}
    result = gather_files(test_dir, extensions)
    assert result == []

def test_gather_files_single_file_match(tmp_path):
    """Verify gathering when the input path is a matching file."""
    f = tmp_path / "test.pdf"
    f.write_text("content")
    
    result = gather_files(f, {"pdf"})
    assert result == [Path("test.pdf")]

def test_gather_files_single_file_no_match(tmp_path):
    """Verify gathering when the input path is a non-matching file."""
    f = tmp_path / "test.txt"
    f.write_text("content")
    
    result = gather_files(f, {"pdf"})
    assert result == []

def test_gather_files_case_insensitivity(test_dir):
    """Verify that extension matching is case-insensitive."""
    (test_dir / "UPPER.PDF").write_text("content")
    
    result = gather_files(test_dir, {"pdf"}, max_depth=-1)
    assert Path("UPPER.PDF") in result

def test_gather_files_leading_dot_normalization(test_dir):
    """Verify that extensions with leading dots are normalized."""
    result = gather_files(test_dir, {".pdf"}, max_depth=-1)
    assert len(result) >= 1
    assert any(p.suffix == ".pdf" for p in result)
