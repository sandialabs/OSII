import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import export_images  # noqa: E402


def test_export_collection_contains_only_selected_images(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, json.dumps([{
                "Os": "linux", "Architecture": "amd64", "Id": "sha256:example",
            }]), "")
        if command[1] == "save":
            Path(command[command.index("--output") + 1]).write_bytes(b"image archive")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(export_images.subprocess, "run", fake_run)
    destination = tmp_path / "offline"
    manifest = export_images.export_images(
        runtime="podman", prefix="quay.example/team/osii", tag="1.2.3",
        toolbox=["llm-wikis"], output_dir=destination, platform="linux/amd64",
    )

    assert [entry["reference"] for entry in manifest["images"]] == [
        "quay.example/team/osii-core:1.2.3",
        "quay.example/team/osii-dashboard:1.2.3",
        "quay.example/team/osii-baseline-processors:1.2.3",
        "quay.example/team/osii-llm-wikis:1.2.3",
    ]
    assert "--multi-image-archive" in calls[-1]
    assert (destination / "osii-images.tar").read_bytes() == b"image archive"
    assert json.loads((destination / "manifest.json").read_text()) == manifest
    assert manifest["sha256"] == export_images.file_sha256(destination / "osii-images.tar")
    with pytest.raises(FileExistsError):
        export_images.export_images(
            runtime="podman", prefix="quay.example/team/osii", tag="1.2.3",
            toolbox=[], output_dir=destination,
        )


def test_export_rejects_missing_or_wrong_architecture_before_writing(tmp_path, monkeypatch):
    destination = tmp_path / "offline"

    def missing(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "image not known")

    monkeypatch.setattr(export_images.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="not available locally"):
        export_images.export_images(
            runtime="podman", prefix="localhost/osii", tag="latest",
            toolbox=[], output_dir=destination,
        )
    assert not destination.exists()

    def arm_only(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, json.dumps([{
            "Os": "linux", "Architecture": "arm64", "Id": "sha256:arm",
        }]), "")

    monkeypatch.setattr(export_images.subprocess, "run", arm_only)
    with pytest.raises(ValueError, match="not linux/amd64"):
        export_images.export_images(
            runtime="podman", prefix="localhost/osii", tag="latest",
            toolbox=[], output_dir=destination, platform="linux/amd64",
        )
    assert not destination.exists()


def test_pull_requests_target_platform(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, json.dumps([{
                "Os": "linux", "Architecture": "amd64", "Id": "sha256:example",
            }]), "")
        if command[1] == "save":
            Path(command[command.index("--output") + 1]).write_bytes(b"image archive")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(export_images.subprocess, "run", fake_run)
    export_images.export_images(
        runtime="docker", prefix="quay.example/team/osii", tag="1.2.3",
        toolbox=[], output_dir=tmp_path / "offline", pull=True,
        platform="linux/amd64",
    )
    assert len([command for command in calls if command[1:3] == ["pull", "--platform"]]) == 3
    assert "--multi-image-archive" not in calls[-1]
