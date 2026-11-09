import json
import pytest

from osii.configuration import resolve_tool_models
from osii.domain.artifacts.enrichment_artifacts import write_scope_enrichment_variant
from osii.domain.artifacts.products import (
    edit_product,
    product_path,
    read_product,
    product_provenance,
    activate_product,
)
from osii.domain.artifacts.read_enrichments import (
    get_scope_enrichment_payload,
    list_scope_enrichments,
    delete_scope_enrichment,
)
from osii.domain.processing import jobs
from osii.domain import tool_actions
from osii.worker import execute_job


def wiki(text):
    return {
        "artifact_type": "wiki_markdown",
        "title": "Test wiki",
        "markdown": text,
        "citations": [{"file_id": "source"}],
    }


@pytest.mark.parametrize(
    "scope",
    [
        {"scope_type": "root"},
        {"scope_type": "object", "file_id": "document"},
        {"scope_type": "folder", "folder_id": "folder"},
        {"scope_type": "collection", "collection_id": "collection"},
    ],
)
def test_wiki_edits_keep_history_and_regeneration_candidates(temp_osii_root, scope):
    root = temp_osii_root
    filename = "wiki--test.json"
    write_scope_enrichment_variant(
        root, scope, kind="wiki", method="test", payload=wiki("Original")
    )
    path = product_path(root, scope, filename)
    original = read_product(path)
    edited = edit_product(root, scope, filename, "Human revision", original["current"])
    with pytest.raises(FileExistsError):
        edit_product(root, scope, filename, "Stale draft", original["current"])
    with product_provenance({"run_id": "generation-2"}):
        write_scope_enrichment_variant(
            root, scope, kind="wiki", method="test", payload=wiki("New generation")
        )
        write_scope_enrichment_variant(
            root,
            scope,
            kind="wiki",
            method="test",
            payload=wiki("Duplicate publication"),
        )
    history = read_product(path)
    assert len(history["revisions"]) == 3
    assert history["current"] == edited["current"]
    assert history["data"]["markdown"] == "Human revision"
    assert history["data"]["citations"] == wiki("")["citations"]
    assert (
        get_scope_enrichment_payload(root, scope, filename)["data"] == history["data"]
    )
    assert not any(
        entry["name"].startswith(".") for entry in list_scope_enrichments(root, scope)
    )
    restored = activate_product(
        root, scope, filename, history["revisions"][-1]["id"], history["current"]
    )
    assert restored["data"]["markdown"] == "New generation"
    delete_scope_enrichment(root, scope, filename)
    assert get_scope_enrichment_payload(root, scope, filename) is None
    assert len(read_product(path)["revisions"]) == 4


def test_legacy_wiki_is_imported_without_losing_original(temp_osii_root):
    scope = {"scope_type": "root"}
    path = product_path(temp_osii_root, scope, "wiki--legacy.json")
    path.write_text(json.dumps(wiki("Legacy")))
    original = read_product(path)
    result = edit_product(
        temp_osii_root, scope, path.name, "Edited", original["current"]
    )
    assert result["revisions"][0]["data"]["markdown"] == "Legacy"
    assert result["revisions"][0]["origin"] == "imported"


def test_model_defaults_migrate_only_missing_shipped_aliases(
    temp_osii_root, monkeypatch
):
    import osii.configuration as configuration

    monkeypatch.setattr(
        configuration,
        "tool_for_processor",
        lambda *_: ("wiki", {"model_access": {"bindings": {"chat": "top"}}}),
    )
    connections = {
        "library": {"enabled": True, "capabilities": ["chat"], "model": "default-model"}
    }
    monkeypatch.setattr(
        configuration,
        "load_models_config",
        lambda *_: {"models": connections, "defaults": {"chat": "library"}},
    )
    monkeypatch.setattr(
        configuration, "model_connection", lambda alias, *_: connections.get(alias)
    )
    assert resolve_tool_models(
        "toolbox.readable-wiki", {"chat": "required"}, temp_osii_root
    ) == {"chat": "library"}
    connections["top"] = {"capabilities": ["chat"], "model": "custom-top"}
    assert resolve_tool_models(
        "toolbox.readable-wiki", {"chat": "required"}, temp_osii_root
    ) == {"chat": "top"}
    with pytest.raises(ValueError, match="enabled chat model"):
        resolve_tool_models(
            "toolbox.readable-wiki",
            {"chat": "required"},
            temp_osii_root,
            {"chat": "missing-custom"},
        )


def test_tool_retry_uses_frozen_text_and_does_not_repeat_saved_result(
    temp_osii_root, sample_osii_object, monkeypatch
):
    root, file_id = temp_osii_root, sample_osii_object["file_id"]
    calls = []

    class Method:
        name = "test.method"

        def describe(self):
            return {"version": "1", "display_name": "Test method"}

        def enrich(self, **arguments):
            from osii.enrichment.common import collect_scope_texts

            text = collect_scope_texts(arguments["osii_store"], arguments["scope"])[0][
                0
            ]["text"]
            calls.append(text)
            if len(calls) == 1:
                raise RuntimeError("Transient provider failure")
            return {"ok": True, "result": {"text": text}}

    monkeypatch.setattr(tool_actions, "resolve_enricher", lambda _: Method())
    result = tool_actions.submit_tool(
        root,
        {
            "enricher_name": Method.name,
            "scope": {"scope_type": "object", "file_id": file_id},
        },
    )
    job = jobs.claim_next_queue_job("worker-before-restart")
    with pytest.raises(RuntimeError, match="Transient"):
        execute_job(job)
    jobs.complete_queue_job(job["id"], error="Transient provider failure")
    jobs.control_run(result["run_id"], "retry")
    # A new worker sees the same queued snapshot even after canonical text changes.
    monkeypatch.setattr(
        "osii.enrichment.common.get_preferred_text_representation",
        lambda *_: {"text": "Changed source"},
    )
    job = jobs.claim_next_queue_job("worker-after-restart")
    execute_job(job)
    assert calls[0] == calls[1] == "Thermal calibration drift was reduced."
    execute_job(job)  # Lost completion acknowledgement reuses the committed result.
    assert len(calls) == 2
    assert jobs.get_run(result["run_id"])["status"] == "done"


def test_repeated_human_edits_are_distinct_even_with_generated_provenance(
    temp_osii_root,
):
    scope = {"scope_type": "root"}
    with product_provenance({"run_id": "generated-run"}):
        write_scope_enrichment_variant(
            temp_osii_root, scope, kind="wiki", method="test", payload=wiki("Generated")
        )
    path = product_path(temp_osii_root, scope, "wiki--test.json")
    first = edit_product(
        temp_osii_root, scope, path.name, "First edit", read_product(path)["current"]
    )
    second = edit_product(
        temp_osii_root, scope, path.name, "Second edit", first["current"]
    )
    assert second["data"]["markdown"] == "Second edit"
    assert len(second["revisions"]) == 3


def test_scope_snapshot_is_bounded_and_records_full_source_hash(
    temp_osii_root, sample_osii_object
):
    from osii.enrichment.common import (
        snapshot_scope,
        frozen_scope_inputs,
        collect_scope_texts,
    )
    import hashlib

    scope = {"scope_type": "object", "file_id": sample_osii_object["file_id"]}
    snapshot = snapshot_scope(temp_osii_root, scope, max_chars=8)
    document = snapshot["documents"][0]
    assert document["text"] == "Thermal "
    assert (
        document["source_sha256"]
        == hashlib.sha256(b"Thermal calibration drift was reduced.").hexdigest()
    )
    assert document["truncated"] is True
    assert document["retained_spans"] == [{"start": 0, "end": 8}]
    with frozen_scope_inputs(temp_osii_root, scope, snapshot["documents"]):
        assert collect_scope_texts(temp_osii_root, scope)[1] == 8
    assert collect_scope_texts(temp_osii_root, scope)[1] > 8


def test_tool_model_change_fails_before_provider_call(
    temp_osii_root, sample_osii_object, monkeypatch
):
    class Method:
        name = "test.model-tool"

        def describe(self):
            return {"version": "1", "model_requirements": {"chat": "required"}}

        def enrich(self, **arguments):
            raise AssertionError("Provider must not be invoked")

    connection = {"model": "first", "capabilities": ["chat"]}
    monkeypatch.setattr(tool_actions, "resolve_enricher", lambda _: Method())
    monkeypatch.setattr(
        tool_actions, "resolve_tool_models", lambda *a: {"chat": "selected"}
    )
    monkeypatch.setattr(tool_actions, "model_connection", lambda *a: dict(connection))
    result = tool_actions.submit_tool(
        temp_osii_root,
        {
            "enricher_name": Method.name,
            "scope": {"scope_type": "object", "file_id": sample_osii_object["file_id"]},
        },
    )
    connection["model"] = "second"
    with pytest.raises(ValueError, match="changed since submission"):
        execute_job(jobs.claim_next_queue_job("worker"))
    assert jobs.get_run(result["run_id"])["status"] == "error"


def test_new_wiki_method_appears_from_descriptor_without_ui_registration(
    temp_osii_root, monkeypatch
):
    class Method:
        name = "sme.new-wiki"

        def describe(self):
            return {
                "version": "2",
                "display_name": "SME Wiki",
                "capabilities": {
                    "scope_types": ["collection"],
                    "output_kinds": ["wiki_markdown"],
                },
            }

    monkeypatch.setattr(tool_actions, "get_enrichers", lambda: [Method()])
    monkeypatch.setattr("osii.processors.remote.discover_remote_processors", lambda: [])
    result = tool_actions.tool_catalog(temp_osii_root)
    method = next(item for item in result["methods"] if item["id"] == Method.name)
    assert method["action"] == "wiki.write"
    assert method["scopes"] == ["collection"]
    assert method["execution"] == "scope"


def test_parallel_saves_accept_one_revision_and_preserve_both_drafts(temp_osii_root):
    from concurrent.futures import ThreadPoolExecutor

    scope = {"scope_type": "root"}
    write_scope_enrichment_variant(
        temp_osii_root, scope, kind="wiki", method="test", payload=wiki("Original")
    )
    path = product_path(temp_osii_root, scope, "wiki--test.json")
    expected = read_product(path)["current"]

    def save(text):
        try:
            edit_product(temp_osii_root, scope, path.name, text, expected)
            return "saved"
        except FileExistsError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["First draft", "Second draft"]))
    assert sorted(results) == ["conflict", "saved"]
    assert len(read_product(path)["revisions"]) == 2


def test_default_binding_can_be_restored_without_pin_to_todays_model(temp_osii_root):
    from osii.api.processor_admin_routes import _model_access

    descriptor = {"model_requirements": {"chat": "required"}}
    assert _model_access(
        {"model_connection": "", "model_access": {"bindings": {"chat": "old"}}},
        descriptor,
        temp_osii_root,
    ) == {"mode": "gateway", "bindings": {}}
    assert _model_access({"model_connection": "chosen"}, descriptor, temp_osii_root)[
        "bindings"
    ] == {"chat": "chosen"}


def test_committed_wiki_is_visible_when_compatibility_view_is_missing(temp_osii_root):
    scope = {"scope_type": "root"}
    with product_provenance({"run_id": "saved-run"}):
        write_scope_enrichment_variant(
            temp_osii_root, scope, kind="wiki", method="test", payload=wiki("Committed")
        )
        path = product_path(temp_osii_root, scope, "wiki--test.json")
        path.unlink()  # Compatibility publication was interrupted after commit.
        assert (
            get_scope_enrichment_payload(temp_osii_root, scope, path.name)["data"][
                "markdown"
            ]
            == "Committed"
        )
        assert any(
            item["name"] == path.name
            for item in list_scope_enrichments(temp_osii_root, scope)
        )
        write_scope_enrichment_variant(
            temp_osii_root, scope, kind="wiki", method="test", payload=wiki("Retry")
        )
        assert json.loads(path.read_text())["markdown"] == "Committed"
        assert len(read_product(path)["revisions"]) == 1


def test_revision_api_returns_library_identity_and_rejects_stale_save(
    client, temp_osii_root
):
    scope = {"scope_type": "root"}
    write_scope_enrichment_variant(
        temp_osii_root, scope, kind="wiki", method="test", payload=wiki("Original")
    )
    request = {"scope": scope, "filename": "wiki--test.json"}
    history = client.post("/api/enrichments/revisions", json=request)
    assert history.status_code == 200
    change = {
        **request,
        "expected_revision": history.json()["current"],
        "markdown": "User edit",
    }
    saved = client.put("/api/enrichments/revisions", json=change)
    assert saved.status_code == 200
    assert saved.json()["library_id"] == history.json()["library_id"]
    assert saved.json()["data"]["markdown"] == "User edit"
    assert client.put("/api/enrichments/revisions", json=change).status_code == 409
    assert (
        client.post(
            "/api/enrichments/revisions",
            json={"scope": scope, "filename": "missing.json"},
        ).status_code
        == 404
    )
