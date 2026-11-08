"""Manual bounded-memory scale check; temporary databases are removed on exit.

PYTHONPATH=osii-core osii-env/bin/python osii-core/tests/benchmark_volume.py --counts 1000000 5000000
Add --filesystem-files 100000 to measure real enumeration separately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import threading
import time

from osii.volume.models import Filters, SelectionRequest
from osii.volume.store import VolumeStore
from osii.volume.worker import execute


def measure(count: int, filesystem: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="osii-volume-benchmark-") as directory:
        root = Path(directory) / "source"
        root.mkdir()
        store = VolumeStore(Path(directory) / "volume.sqlite3")
        store.initialize()
        source = store.register_source(root)
        start = time.perf_counter()
        if filesystem:
            for i in range(count):
                (root / f"document-{i:08}.txt").touch()
            prepare = time.perf_counter() - start
            start = time.perf_counter()
            store.new_scan(source["id"])
            execute(store, store.claim("benchmark"), "benchmark", threading.Event())
        else:
            prepare = 0
            with store.connect() as conn:
                for batch in range(0, count, 1000):
                    conn.executemany(
                        """INSERT INTO entries(source_id,path,parent,name,kind,suffix,
                      size_bytes,mtime_ns,ctime_ns,device,inode,observed,seen_token)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            (
                                source["id"],
                                f"folder-{i // 1000:06}/document-{i:08}.txt",
                                f"folder-{i // 1000:06}",
                                f"document-{i:08}.txt",
                                "file",
                                ".txt",
                                4096,
                                1700000000000000000,
                                1700000000000000000,
                                1,
                                i,
                                1700000000,
                                "benchmark",
                            )
                            for i in range(batch, min(count, batch + 1000))
                        ),
                    )
                    conn.commit()
        inventory_seconds = time.perf_counter() - start
        start = time.perf_counter()
        page = store.entries(Filters(suffix="txt"), max(0, count - 101), 100)
        page_ms = (time.perf_counter() - start) * 1000
        assert len(page["items"]) == min(100, count)
        start = time.perf_counter()
        summary = store.summary(Filters())
        summary_seconds = time.perf_counter() - start
        assert summary["files"] == count
        start = time.perf_counter()
        selected = store.select(SelectionRequest(sample=True, max_files=100))
        sample_seconds = time.perf_counter() - start
        assert selected["count"] <= 100
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KiB.
        peak_mib = peak / (1024**2 if sys.platform == "darwin" else 1024)
        return {
            "files": count,
            "filesystem": filesystem,
            "prepare_seconds": round(prepare, 3),
            "inventory_seconds": round(inventory_seconds, 3),
            "page_ms": round(page_ms, 3),
            "summary_seconds": round(summary_seconds, 3),
            "sample_seconds": round(sample_seconds, 3),
            "peak_rss_mib": round(peak_mib, 1),
            "database_mib": round(store.path.stat().st_size / 1024**2, 1),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--counts", nargs="+", type=int, default=[1_000_000, 5_000_000])
    parser.add_argument("--filesystem-files", type=int, default=0)
    parser.add_argument("--child", type=int)
    parser.add_argument("--filesystem", action="store_true")
    args = parser.parse_args()
    if args.child is not None:
        print(json.dumps(measure(args.child, args.filesystem)), flush=True)
    else:
        for count in args.counts:
            subprocess.run(
                [sys.executable, __file__, "--child", str(count)], check=True
            )
        if args.filesystem_files:
            subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "--child",
                    str(args.filesystem_files),
                    "--filesystem",
                ],
                check=True,
            )
