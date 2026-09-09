import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from osii.main import app
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.folders import write_folder_manifest
from osii.domain.storage.objects import append_manifest_record, write_meta_toml, write_text_file
from osii.domain.storage.store import ensure_osii_store_layout


@pytest.fixture
def temp_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_volume" / "my_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def temp_osii_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_volume" / ".osii"
    ensure_osii_store_layout(root)
    return root


@pytest.fixture
def temp_upload_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_volume" / "uploaded_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def test_app(temp_data_root: Path, temp_osii_root: Path, temp_upload_root: Path):
    app.state.shared_volume_root = temp_data_root
    app.state.shared_volume_host_path = str(temp_data_root)
    app.state.osii_root = temp_osii_root
    app.state.upload_originals_root = temp_upload_root
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def sample_osii_object(temp_osii_root: Path):
    file_id = "sha256-test123"
    root_folder_id = "folder-root"
    source_relpath = "example_data/purcell.pdf"

    write_root_toml(
        temp_osii_root,
        root_folder_id=root_folder_id,
        host_path="C:/fake/data_root",
        container_path="/data_root",
        notes="test root",
        tool_versions={"pipeline_version": "test"},
    )

    write_folder_manifest(
        temp_osii_root,
        folder_id=root_folder_id,
        path_hint="",
        docs=[{"source_relpath": source_relpath, "file_id": file_id}],
        subfolders=[],
        stats={
            "file_count": 1,
            "subfolder_count": 0,
            "total_bytes": 1234,
            "latest_mtime_utc": "2026-05-21T00:00:00Z",
        },
        entrypoints=None,
    )

    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath=source_relpath,
        filename="example_data/purcell.pdf",
        mime="application/pdf",
        size_bytes=1234,
        mtime_utc="2026-05-21T00:00:00Z",
        sha256_hex="test123",
        extra_meta=None,
    )

    full_text = "Thermal calibration drift was reduced."
    write_text_file(temp_osii_root, file_id, full_text)

    append_manifest_record(
        temp_osii_root,
        file_id,
        {
            "kind": "text",
            "id": "seg-000001",
            "path": "text.txt",
            "type": "page",
            "span": {
                "char_start": 0,
                "char_end": len(full_text),
            },
            "source_origin": {
                "source_type": "pdf",
                "unit_type": "page",
                "page": 1,
            },
            "related_ids": [],
        },
    )

    synth_txt = temp_osii_root / "objects" / file_id / "synth.txt"
    synth_txt.write_text(
        "This appears to be a technical report about thermal calibration drift.",
        encoding="utf-8",
    )

    synth_toml = temp_osii_root / "objects" / file_id / "synth.toml"
    synth_toml.write_text(
        """
[path]
source_relpath = "example_data/purcell.pdf"

[synthesis]
synthesis = "Technical report about thermal calibration drift."
doc_type = "technical report"
quality = "default"

[details]
description = "This appears to be a technical report about thermal calibration drift."
""".strip(),
        encoding="utf-8",
    )

    return {
        "file_id": file_id,
        "root_folder_id": root_folder_id,
        "source_relpath": source_relpath,
    }