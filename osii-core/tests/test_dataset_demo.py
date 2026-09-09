from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_example_dataset_archive_is_safely_unpackable(tmp_path: Path, monkeypatch):
    importer = _load_module(
        "osii_import_example_data_test",
        REPOSITORY_ROOT / "scripts" / "import_example_data.py",
    )
    dataset = importer.DatasetExport(
        slug="tiny",
        display_name="Tiny dataset",
        description="A test dataset.",
        feature_names=["measurement"],
        target_name="target_class",
        target_names=["first", "second"],
        rows=[[1.5], [2.5]],
        targets=[0, 1],
    )
    archive = tmp_path / "tiny.zip"
    importer.build_dataset_archive(dataset, archive)
    written = importer.unpack_dataset_archive(archive, tmp_path / "output")

    csv_paths = sorted(path for path in written if path.suffix == ".csv")
    assert [path.name for path in csv_paths] == ["first.csv", "second.csv"]
    metadata = json.loads((tmp_path / "output" / "tiny" / "dataset.json").read_text())
    assert metadata["row_count"] == 2

    configured = tmp_path / "configured-source"
    monkeypatch.setenv("OSII_SOURCE_DIR", str(configured))
    assert importer.configured_destination() == configured
