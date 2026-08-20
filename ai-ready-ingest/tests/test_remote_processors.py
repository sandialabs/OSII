from pathlib import Path
import tomllib

from osii_processor_sdk import (
    Capability,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    SynthesisResponse,
)

from osii.processors import remote


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


def test_shirty_provider_uses_bundled_http_adapters_without_fake_embedding(tmp_path, monkeypatch):
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    monkeypatch.setenv("OSII_MODEL_BRIDGE_URL", "http://model-bridge:8095")
    state = tmp_path / "state"
    state.mkdir()
    (state / "model_providers.json").write_text(
        '[{"id":"shirty-corporate","type":"shirty","base_url":"https://shirty.example/api/v1","enabled":true}]',
        encoding="utf-8",
    )

    urls = remote.configured_processor_urls()

    assert urls == [
        "http://model-bridge:8095/shirty/extractor",
        "http://model-bridge:8095/shirty/synthesizer",
    ]
    assert not any("embedder" in url for url in urls)


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
        display_name="Local Extractive Preview",
        description="Test synthesizer",
        kind=ProcessorKind.SYNTHESIZER,
        capabilities=Capability(scope_types=["object"]),
    ).model_dump(mode="json")
    synthesizer = remote.RemoteSynthesizer(
        {**descriptor, "base_url": "http://synthesizer.test"}
    )

    class FakeClient:
        def synthesize(self, request):
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
