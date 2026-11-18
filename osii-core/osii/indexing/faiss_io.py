"""Preserve FAISS's binary format with Python's Unicode-capable file handles.

FAISS's filename overload uses narrow C paths on Windows. Python callbacks
avoid that limitation without copying an entire index into a bytes buffer.
https://github.com/facebookresearch/faiss/wiki/Index-IO%2C-cloning-and-hyper-parameter-tuning
"""
from pathlib import Path

import faiss


def read_index(path: Path) -> faiss.Index:
    with path.open("rb") as stream:
        return faiss.read_index(faiss.PyCallbackIOReader(stream.read))


def write_index(index: faiss.Index, path: Path) -> None:
    with path.open("wb") as stream:
        faiss.write_index(index, faiss.PyCallbackIOWriter(stream.write))
