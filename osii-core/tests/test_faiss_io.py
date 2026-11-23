import faiss
import numpy as np
import pytest

from osii.indexing.faiss_io import read_index, write_index


def test_unicode_index_paths_preserve_native_format_and_search(tmp_path):
    directory = tmp_path / "Résumé — 索引 with spaces"
    directory.mkdir()
    target = directory / "segments.faiss"
    vectors = np.array([[1, 0, 0], [0, 1, 0]], dtype="float32")
    index = faiss.IndexFlatIP(3)
    index.add(vectors)
    write_index(index, target)
    assert target.read_bytes() == faiss.serialize_index(index).tobytes()
    reopened = read_index(target)
    assert reopened.ntotal == 2
    _, hits = reopened.search(vectors[1:], 1)
    assert int(hits[0, 0]) == 1
    np.testing.assert_array_equal(reopened.reconstruct(0), vectors[0])


def test_a_corrupt_index_closes_its_file_handle(tmp_path):
    target = tmp_path / "corrupt.faiss"
    target.write_bytes(b"not an index")
    with pytest.raises(RuntimeError):
        read_index(target)
    target.unlink()  # Windows refuses this if a failed read leaked its handle.
