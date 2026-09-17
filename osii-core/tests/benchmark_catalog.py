"""Manual 1k/10k catalog benchmark: `python tests/benchmark_catalog.py`."""

from pathlib import Path
import tempfile
import time

from osii.domain.catalog_db import list_documents, rebuild_catalog
from osii.domain.storage.folders import write_folder_manifest


for count in (1_000, 10_000):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / ".osii"
        started = time.perf_counter()
        write_folder_manifest(root, "root", "", [{"source_relpath": f"experiments/{index:05}.csv", "file_id": f"file-{index:05}"} for index in range(count)], [], None, None)
        rebuilt = rebuild_catalog(root)
        rebuild_seconds = time.perf_counter() - started
        started = time.perf_counter()
        page = list_documents(root, limit=100, suffix="csv", text="001")
        query_ms = (time.perf_counter() - started) * 1000
        print(f"{count:>6} documents: rebuild={rebuild_seconds:.3f}s filtered-page={query_ms:.1f}ms matches={page['total']}")
