from pathlib import Path
import json
import tomllib

from osii.processor_sdk import (
    Capability,
    ExtractionResponse,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    SynthesisResponse,
    TextSegment,
)

from osii.processors import remote
from osii.expert_context import save_expert_context


def test_configured_processor_urls(monkeypatch):
    monkeypatch.setenv(
        "OSII_PROCESSORS",
        "http://processor-a:8000/, http://processor-b:8000",
    )
    assert remote.configured_processor_urls() == [
        "http://processor-a:8000",
        "http://processor-b:8000",
    ]


def test_configured_processor_urls_includes_enabled_admin_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("OSII_PROCESSORS", "http://processor-a:8000")
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    state = tmp_path / "state"
    state.mkdir()
    (state / "processor_endpoints.json").write_text(
        '[{"id":"custom", "base_url":"http://custom:8000/", "enabled":true}, '
        '{"id":"disabled", "base_url":"http://disabled:8000", "enabled":false}]',
        encoding="utf-8",
    )

    assert remote.configured_processor_urls() == [
        "http://processor-a:8000",
        "http://custom:8000",
    ]


def test_openai_provider_uses_standard_embedding_and_synthesis_adapters(tmp_path, monkeypatch):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OSII_MODEL_BRIDGE_URL", "http://model-bridge:8095")
    state = tmp_path / "state"
    state.mkdir()
    (state / "model_providers.json").write_text(
        '[{"id":"openai-corporate","type":"openai","base_url":"https://openai.example/api/v1","enabled":true}]',
        encoding="utf-8",
    )

    urls = remote.configured_processor_urls()

    assert urls == [
        "http://model-bridge:8095/openai/embedder",
        "http://model-bridge:8095/openai/synthesizer",
    ]
    assert not any("extractor" in url for url in urls)


def test_discovery_ignores_unavailable_processors(monkeypatch):
    monkeypatch.setenv("OSII_PROCESSORS", "http://unavailable")

    def fail(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(remote, "_request_json", fail)
    assert remote.discover_remote_processors() == []
    assert remote.discover_remote_processors(include_errors=True)[0]["error"]


def test_remote_synthesis_omits_absent_citation_fields_from_toml(
    temp_osii_root: Path,
    sample_osii_object: dict,
):
    descriptor = ProcessorDescriptor(
        name="local.extractive-preview",
        version="1.0.0",
        display_name="Cited source-excerpt preview (no AI)",
        description="Test synthesizer",
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(scope_types=["object"]),
    ).model_dump(mode="json")
    synthesizer = remote.RemoteSynthesizer(
        {**descriptor, "base_url": "http://synthesizer.test"}
    )
    save_expert_context(
        temp_osii_root,
        {"scope_type": "object", "file_id": sample_osii_object["file_id"]},
        "Temperature readings are in kelvin.",
    )

    class FakeClient:
        def synthesize(self, request):
            assert request.expert_context == "Temperature readings are in kelvin."
            return SynthesisResponse(
                request_id=request.request_id,
                processor=ProcessorDescriptor.model_validate(descriptor),
                markdown="Grounded preview.",
                citations=[ProvenanceRef(file_id=sample_osii_object["file_id"])],
            )

    synthesizer._client = FakeClient()
    result = synthesizer.synthesize(
        osii_store=temp_osii_root,
        file_id=sample_osii_object["file_id"],
    )

    assert result["error"] is None
    provenance = tomllib.loads(
        (
            temp_osii_root
            / "objects"
            / sample_osii_object["file_id"]
            / "provenance.toml"
        ).read_text(encoding="utf-8")
    )
    assert provenance["synthesis"]["config"]["citations"] == [
        {"file_id": sample_osii_object["file_id"], "source_origin": {}}
    ]
    assert provenance["synthesis"]["config"]["expert_context"] == "Temperature readings are in kelvin."


def test_remote_extractor_receives_saved_context_in_standard_field(tmp_path):
    from osii.domain.storage.ids import compute_file_id

    source = tmp_path / "image.txt"
    source.write_text("placeholder for bounded source bytes", encoding="utf-8")
    store = tmp_path / ".osii"
    file_id = compute_file_id(source)
    save_expert_context(store, {"scope_type": "object", "file_id": file_id}, "SEM, microns.")
    descriptor = ProcessorDescriptor(
        name="example.vlm", version="1.0.0", display_name="Example VLM",
        description="Context-aware image description", kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(scope_types=["object"]),
    )
    extractor = remote.RemoteExtractor({**descriptor.model_dump(mode="json"), "base_url": "http://vlm.test"})

    class FakeClient:
        def extract(self, request):
            assert request.expert_context == "SEM, microns."
            assert request.document.content_base64
            assert "expert_context" not in request.config
            return ExtractionResponse(
                request_id=request.request_id, processor=descriptor,
                segments=[TextSegment(id="region-1", text="A visible crack.", source_origin={"page": 1})],
            )

    extractor._client = FakeClient()
    extractor.extract(source_path=source, data_volume_root=tmp_path, osii_store=store)
    provenance = tomllib.loads((store / "objects" / file_id / "provenance.toml").read_text(encoding="utf-8"))
    assert provenance["config"]["expert_context"] == "SEM, microns."
    assert provenance["config"]["expert_context_supplied"] is True


def test_remote_enricher_commits_multiple_standard_artifacts_by_kind(
    temp_osii_root: Path,
    sample_osii_object: dict,
    monkeypatch,
):
    descriptor = ProcessorDescriptor(
        name="toolbox.concept-entity-wiki",
        version="1.0.0",
        display_name="Concept and entity LLM wiki",
        description="Test enricher",
        kind=ProcessorKind.ENRICHER,
        capabilities=Capability(
            scope_types=["object"],
            output_kinds=["wiki_markdown", "entity_list", "table"],
        ),
    ).model_dump(mode="json")
    enricher = remote.RemoteEnricher(
        {**descriptor, "base_url": "http://wiki.test"}
    )

    def fake_request(url, *, payload=None, timeout=120.0):
        assert url == "http://wiki.test/v1/enrich"
        assert payload["scope"]["documents"][0]["text"] == "Thermal calibration drift was reduced."
        return {
            "request_id": payload["request_id"],
            "processor": descriptor,
            "metadata": {"model": "test-model", "provider": "test"},
            "artifacts": [
                {
                    "id": "concept-entity-wiki", "kind": "wiki",
                    "standard_data": {
                        "artifact_type": "wiki_markdown", "title": "Wiki",
                        "markdown": "# Wiki", "citations": [],
                    },
                },
                {
                    "id": "entities", "kind": "entities",
                    "standard_data": {
                        "artifact_type": "entity_list", "title": "Entities",
                        "entities": [],
                    },
                },
                {
                    "id": "concepts", "kind": "table",
                    "standard_data": {
                        "artifact_type": "table", "title": "Concepts",
                        "columns": [], "rows": [], "row_provenance": [],
                    },
                },
            ],
        }

    monkeypatch.setattr(remote, "_request_json", fake_request)
    result = enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": sample_osii_object["file_id"]},
    )

    assert len(result["artifacts"]) == 3
    directory = temp_osii_root / "objects" / sample_osii_object["file_id"] / "enrichments"
    assert (directory / "wiki--toolbox.concept-entity-wiki.json").is_file()
    assert (directory / "entities--toolbox.concept-entity-wiki.json").is_file()
    assert (directory / "table--toolbox.concept-entity-wiki.json").is_file()
    metadata = json.loads(
        (directory / "wiki--toolbox.concept-entity-wiki.meta.json").read_text()
    )
    assert metadata["model"] == "test-model"
    assert metadata["provider"] == "test"
