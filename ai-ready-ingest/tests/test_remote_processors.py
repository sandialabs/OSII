from pathlib import Path
import tomllib

from osii_processor_sdk import (
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
