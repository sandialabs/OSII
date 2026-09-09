from pathlib import Path
import tomllib

import pytest

from osii.domain.artifacts.extraction_variants import (
    extract_document_variant,
    promote_extraction_variant,
)
from osii.expert_context import (
    expert_context_path,
    load_expert_context,
    resolve_expert_context,
    save_expert_context,
)


@pytest.mark.parametrize("scope,relative", [
    ({"scope_type": "root"}, "expert-context.md"),
    ({"scope_type": "object", "file_id": "sha256-example"}, "objects/sha256-example/expert-context.md"),
    ({"scope_type": "folder", "folder_id": "lab"}, "folders/folder-lab.expert-context.md"),
    ({"scope_type": "collection", "collection_id": "col-lab"}, "collections/col-lab/expert-context.md"),
])
def test_context_is_portable_text_reused_until_explicitly_cleared(tmp_path, scope, relative):
    assert load_expert_context(tmp_path, scope) is None
    assert not list(tmp_path.iterdir())
    path = save_expert_context(tmp_path, scope, "  Magnification is 20×.  ")
    assert path == tmp_path / relative
    assert path.read_text(encoding="utf-8") == "Magnification is 20×.\n"
    assert resolve_expert_context(tmp_path, scope, None) == "Magnification is 20×."
    assert resolve_expert_context(tmp_path, scope, " ") == "Magnification is 20×."
    assert resolve_expert_context(tmp_path, scope, "New guidance") == "New guidance"
    save_expert_context(tmp_path, scope, "")
    assert load_expert_context(tmp_path, scope) is None


def test_context_is_not_implicitly_inherited_by_unrelated_scopes(tmp_path):
    save_expert_context(tmp_path, {"scope_type": "root"}, "Library-only guidance")
    assert load_expert_context(tmp_path, {"scope_type": "object", "file_id": "other"}) is None


@pytest.mark.parametrize("identifier", ["..", "../outside", "folder/file", "C:\\private", "", "/tmp"])
def test_context_rejects_unsafe_scope_ids(tmp_path, identifier):
    with pytest.raises(ValueError):
        expert_context_path(tmp_path, {"scope_type": "object", "file_id": identifier})


def test_context_rejects_invalid_or_excessive_text(tmp_path):
    scope = {"scope_type": "root"}
    with pytest.raises(ValueError):
        resolve_expert_context(tmp_path, scope, {"not": "text"})
    with pytest.raises(ValueError):
        save_expert_context(tmp_path, scope, "x" * 20_001)


def test_extraction_keeps_context_and_historical_snapshots(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Original source evidence", encoding="utf-8")
    store = tmp_path / ".osii"
    arguments = dict(
        extractor_name="native_text", source_path=source,
        data_volume_root=tmp_path, osii_root=store,
    )
    first = extract_document_variant(**arguments, expert_context="Calibration image: 20×.")
    scope = {"scope_type": "object", "file_id": first["file_id"]}
    second = extract_document_variant(**arguments, expert_context="Calibration image: 40×.")
    # Promoting a historical extraction does not overwrite current guidance.
    promote_extraction_variant(store, first["file_id"], first["variant_id"])
    assert load_expert_context(store, scope) == "Calibration image: 40×."
    for result, context in [(first, "Calibration image: 20×."), (second, "Calibration image: 40×.")]:
        bundle = store / "objects" / result["file_id"] / "extractions" / result["variant_id"]
        assert (bundle / "expert-context.md").read_text(encoding="utf-8").strip() == context
        provenance = tomllib.loads((bundle / "provenance.toml").read_text(encoding="utf-8"))
        assert provenance["config"]["expert_context"] == context
        assert provenance["config"]["expert_context_used"] is False
        assert "Calibration" not in (bundle / "text.txt").read_text(encoding="utf-8")

    # A later VLM receives the same guidance, despite an omitted context field.
    def fake_vlm(**kwargs):
        from osii.extraction.dispatcher import dispatch_extract
        assert kwargs["expert_context"] == "Calibration image: 40×."
        kwargs["extractor_name"] = "native_text"
        return dispatch_extract(**kwargs)

    extract_document_variant(**arguments, dispatcher=fake_vlm)


def test_failed_extractor_does_not_lose_saved_context(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("source", encoding="utf-8")
    store = tmp_path / ".osii"

    def unavailable(**kwargs):
        raise RuntimeError("VLM offline")

    with pytest.raises(RuntimeError, match="VLM offline"):
        extract_document_variant(
            extractor_name="example.vlm", source_path=source,
            data_volume_root=tmp_path, osii_root=store,
            expert_context="SEM images, scale in microns.", dispatcher=unavailable,
        )
    contexts = list((store / "objects").glob("*/expert-context.md"))
    assert len(contexts) == 1
    assert contexts[0].read_text(encoding="utf-8").strip() == "SEM images, scale in microns."


@pytest.mark.parametrize("kind", ["root", "object"])
def test_llm_wiki_reuses_context_without_treating_it_as_source_text(
    temp_osii_root, sample_osii_object, monkeypatch, kind,
):
    import json
    from osii.enrichment import llm_wiki
    from osii_processor_sdk import Capability, ProcessorDescriptor, ProcessorKind, SynthesisResponse

    scope = {"scope_type": kind}
    if kind == "object":
        scope["file_id"] = sample_osii_object["file_id"]
    context = "Expert guidance: readings are in kelvin."
    save_expert_context(temp_osii_root, scope, context)
    descriptor = ProcessorDescriptor(
        name="example.synthesis", version="1.0.0", display_name="Example LLM",
        description="Test", kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(scope_types=["root", "object"]),
    )

    class FakeClient:
        def synthesize(self, request):
            assert context in request.expert_context
            assert all(context not in (document.text or "") for document in request.scope.documents)
            return SynthesisResponse(request_id=request.request_id, processor=descriptor, markdown="# Wiki\n\nSource overview.")

    monkeypatch.setattr(llm_wiki, "ProcessorClient", lambda url: FakeClient())
    monkeypatch.setattr(llm_wiki, "resolve_remote_processor", lambda *args: {"base_url": "http://test"})
    result = llm_wiki.LlmWikiEnricher().enrich(
        osii_store=temp_osii_root, scope=scope,
        enricher_config={"synthesizer_name": "example.synthesis"},
    )
    metadata = json.loads((temp_osii_root / result["result"]["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["expert_context"] == context
