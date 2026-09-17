from __future__ import annotations

from pathlib import Path

from osii.domain.processing.source_access import source_access_summary, source_kind


def test_explicit_shared_source_uses_separate_writable_artifact_root(tmp_path: Path):
    source = tmp_path / "mounted-share"
    artifacts = tmp_path / "local-state" / ".osii"
    source.mkdir()
    artifacts.mkdir(parents=True)

    summary = source_access_summary(source, artifacts, configured_kind="shared")

    assert summary["kind"] == "shared"
    assert summary["available"] is True
    assert summary["ready_for_intake"] is True
    assert summary["osii_root"] == str(artifacts)
    assert "reads originals in place" in summary["detail"]


def test_unc_path_is_recognized_as_shared_without_contacting_server():
    assert source_kind(Path(r"\\server\department\documents")) == "shared"


def test_unavailable_share_has_actionable_status(tmp_path: Path):
    source = tmp_path / "disconnected-share"
    artifacts = tmp_path / ".osii"
    artifacts.mkdir()

    summary = source_access_summary(source, artifacts, configured_kind="shared")

    assert summary["available"] is False
    assert summary["source_mode"] == "unavailable"
    assert summary["ready_for_intake"] is False
    assert "not currently available" in summary["detail"]


def test_intake_readiness_reports_source_and_artifact_locations(client, test_app):
    test_app.state.source_kind = "shared"

    response = client.get("/api/intake/readiness")

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["kind"] == "shared"
    assert source["source_root"] == str(test_app.state.shared_volume_root)
    assert source["osii_root"] == str(test_app.state.osii_root)
    assert source["ready_for_intake"] is True
