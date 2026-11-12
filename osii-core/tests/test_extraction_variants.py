from pathlib import Path

from osii.domain.artifacts.extraction_variants import (
    extract_document_variant,
    list_extraction_artifacts,
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


def test_extraction_artifact_api_previews_standard_json(
    client,
    temp_data_root: Path,
    temp_osii_root: Path,
):
    source = temp_data_root / "measurements.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    extraction = extract_document_variant(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=temp_data_root.parent,
        osii_root=temp_osii_root,
        make_primary=True,
    )
    bundle = (
        temp_osii_root
        / "objects"
        / extraction["file_id"]
        / "extractions"
        / extraction["variant_id"]
    )
    artifact = bundle / "artifacts" / "artifact-000001.json"
    artifact.write_text(
        '{"artifact_type":"table","title":"Measurements","columns":[],"rows":[]}',
        encoding="utf-8",
    )
    with (bundle / "manifest.jsonl").open("a", encoding="utf-8") as manifest:
        manifest.write(
            '{"kind":"table","id":"source-table","path":"artifacts/artifact-000001.json",'
            '"type":"application/json","source_origin":{"row":1}}\n'
        )

    listed = list_extraction_artifacts(
        temp_osii_root,
        extraction["file_id"],
        extraction["variant_id"],
    )
    assert listed[0]["data"]["artifact_type"] == "table"

    response = client.get(
        f"/api/objects/{extraction['file_id']}/extractions/"
        f"{extraction['variant_id']}/artifacts"
    )
    assert response.status_code == 200
    assert response.json()["artifacts"][0]["id"] == "source-table"


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


def test_auto_keeps_text_layer_when_adding_another_method(client, temp_data_root, temp_osii_root):
    from osii.extraction.common import init_doc_context, initialize_bundle, persist_segment, update_provenance, build_result_dict
    from osii.extraction.base import ExtractionSegment, ExtractionState
    source = temp_data_root / "sample.txt"
    source.write_text("Original PDF text")
    def dispatcher(*, extractor_name, source_path, data_volume_root, osii_store, **kwargs):
        context = init_doc_context(source_path, data_volume_root)
        initialize_bundle(osii_store=osii_store, doc_ctx=context)
        text = "Original PDF text" if extractor_name == "text-layer" else "Supplemental OCR"
        origin = {"page": 2, "bbox": [0.1, 0.2, 0.7, 0.4], "confidence": 0.91, "coordinate_space": "normalized-page", "custom_instrument": "retained"}
        persist_segment(osii_store=osii_store, doc_ctx=context, segment=ExtractionSegment(seg=1, type="text", text=text, source_origin=origin))
        update_provenance(osii_store=osii_store, doc_ctx=context, extractor_name=extractor_name, extractor_version="1", status="done", tools={}, config={}, state=ExtractionState())
        return build_result_dict(context)
    args = dict(source_path=source, data_volume_root=temp_data_root.parent, osii_root=temp_osii_root, dispatcher=dispatcher)
    first = extract_document_variant(extractor_name="text-layer", **args)
    ocr = extract_document_variant(extractor_name="ocr", **args)
    assert first["made_primary"] is True and ocr["made_primary"] is False
    state = list_extraction_variants(temp_osii_root, first["file_id"])
    assert state["primary_id"] == first["variant_id"]
    assert (temp_osii_root / "objects" / first["file_id"] / "text.txt").read_text() == "Original PDF text"
    saved = client.get(f"/api/objects/{first['file_id']}/extractions/{ocr['variant_id']}/texts")
    assert saved.status_code == 200
    assert saved.json()["text"] == "Supplemental OCR"
    assert saved.json()["segments"][0]["source_origin"]["custom_instrument"] == "retained"
    assert saved.json()["segments"][0]["source_origin"]["confidence"] == 0.91
    assert client.get(f"/api/objects/{first['file_id']}/extractions/missing/texts").status_code == 404
    from osii.domain.processing.jobs import get_run
    queued = client.post(f"/api/objects/{first['file_id']}/extractions", json={"extractor_name": "native_text"}).json()
    assert get_run(queued["run_id"])["operations"]["extraction_policy"] == "save_variant"
    rerun = extract_document_variant(extractor_name="text-layer", **args)
    assert rerun["made_primary"]
