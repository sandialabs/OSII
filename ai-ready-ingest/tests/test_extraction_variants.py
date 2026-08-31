from pathlib import Path

from osii.domain.artifacts.extraction_variants import (
    extract_document_variant,
    list_extraction_variants,
    promote_extraction_variant,
)


def test_reextraction_creates_versions_without_appending_canonical_text(
    temp_data_root: Path,
    temp_osii_root: Path,
):
    source = temp_data_root / "report.txt"
    source.write_text("one clean extraction", encoding="utf-8")

    first = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )
    second = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=False,
    )

    state = list_extraction_variants(temp_osii_root, first["file_id"])
    assert state is not None
    assert state["primary_id"] == first["variant_id"]
    assert len(state["variants"]) == 2
    canonical = temp_osii_root / "objects" / first["file_id"] / "text.txt"
    assert canonical.read_text(encoding="utf-8") == "one clean extraction"

    promoted = promote_extraction_variant(temp_osii_root, first["file_id"], second["variant_id"])
    assert promoted["primary_id"] == second["variant_id"]
    assert canonical.read_text(encoding="utf-8") == "one clean extraction"
    stale = temp_osii_root / "objects" / first["file_id"] / "artifact_staleness.json"
    assert stale.is_file()


def test_extraction_variant_api_can_promote(client, temp_data_root: Path, temp_osii_root: Path):
    source = temp_data_root / "notes.txt"
    source.write_text("versioned notes", encoding="utf-8")
    first = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )
    second = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=False,
    )

    listed = client.get(f"/api/objects/{first['file_id']}/extractions")
    assert listed.status_code == 200
    assert len(listed.json()["variants"]) == 2

    promoted = client.post(
        f"/api/objects/{first['file_id']}/extractions/{second['variant_id']}/primary"
    )
    assert promoted.status_code == 200
    assert promoted.json()["primary_id"] == second["variant_id"]


def test_document_extraction_api_queues_only_the_selected_extractor(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    source = temp_data_root / "queued.txt"
    source.write_text("queue this extraction", encoding="utf-8")
    first = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )

    queued = client.post(
        f"/api/objects/{first['file_id']}/extractions",
        json={
            "extractor_name": "local.native-text",
            "extraction_policy": "save_variant",
        },
    )

    assert queued.status_code == 200
    payload = queued.json()
    assert payload["status"] == "queued"
    run = client.get(f"/api/runs/{payload['run_id']}").json()
    assert run["operations"] == {
        "extract": True,
        "extract_mode": "reprocess",
        "extraction_policy": "save_variant",
        "synthesize": None,
        "embed": False,
        "chunking": None,
        "enrich": None,
    }


def test_document_extraction_api_rejects_a_missing_original(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    source = temp_data_root / "moved.txt"
    source.write_text("move this original", encoding="utf-8")
    first = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )
    source.rename(temp_data_root / "new-location.txt")

    response = client.post(
        f"/api/objects/{first['file_id']}/extractions",
        json={"extractor_name": "local.native-text"},
    )

    assert response.status_code == 409
    assert "rescan source paths" in response.json()["detail"]


def test_library_plan_skips_documents_without_extraction(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    extracted = temp_data_root / "extracted.txt"
    missing = temp_data_root / "missing.txt"
    extracted.write_text("already available", encoding="utf-8")
    missing.write_text("not extracted", encoding="utf-8")
    extract_document_variant(
        extractor_name="native_text",
        source_path=extracted,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )

    preview = client.post(
        "/api/resolve",
        json={
            "queue_paths": [str(temp_data_root)],
            "workflow": "library",
            "run_extraction": False,
            "synthesizer_name": "firstN",
        },
    )
    assert preview.status_code == 200
    plan = preview.json()["preview"]["processing_plan"]
    assert plan["matched_count"] == 2
    assert plan["blocked_count"] == 1

    queued = client.post(
        "/api/runs",
        json={
            "queue_paths": [str(temp_data_root)],
            "workflow": "library",
            "run_extraction": False,
            "synthesizer_name": "firstN",
        },
    )
    assert queued.status_code == 200
    assert queued.json()["resolved_count"] == 1
