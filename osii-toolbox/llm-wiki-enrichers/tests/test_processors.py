from __future__ import annotations

import json

from fastapi.testclient import TestClient

from osii.processor_sdk import (
    Capability,
    DocumentInput,
    EnrichmentRequest,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    ScopeInput,
    SynthesisResponse,
)
from wiki_enrichers.main import concept_entity_app, readable_app
from wiki_enrichers.processors import ConceptEntityWikiEnricher, ReadableWikiEnricher


SYNTHESIZER = ProcessorDescriptor(
    name="test.synthesizer",
    version="1.0.0",
    display_name="Test synthesizer",
    description="A deterministic test double.",
    kind=ProcessorKind.SYNTHESIZER,
    capabilities=Capability(scope_types=["object", "folder", "collection", "root"]),
)


class FakeClient:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.requests = []

    def synthesize(self, request):
        self.requests.append(request)
        return SynthesisResponse(
            request_id=request.request_id,
            processor=SYNTHESIZER,
            markdown=self.markdown,
            citations=[ProvenanceRef(file_id="sha256-a")],
            metadata={"provider": "test", "model": "test-model"},
        )


def request() -> EnrichmentRequest:
    return EnrichmentRequest(
        request_id="enrich-1",
        scope=ScopeInput(
            scope_type="collection",
            scope_id="col-demo",
            documents=[
                DocumentInput(
                    file_id="sha256-a",
                    filename="report-a.txt",
                    text="Project Atlas uses Sensor A. Thermal drift affects Sensor A.",
                ),
                DocumentInput(
                    file_id="sha256-b",
                    filename="report-b.txt",
                    text="Project Beacon documents calibration procedures.",
                ),
            ],
        ),
        expert_context="Treat Atlas and Beacon as project names.",
    )


def test_readable_wiki_returns_one_standard_markdown_artifact() -> None:
    fake = FakeClient("## Overview\n\nProject Atlas uses Sensor A [sha256-a].")
    result = ReadableWikiEnricher(lambda _url, _timeout: fake).enrich(request())

    wiki = result.artifacts[0].standard_data
    assert wiki.artifact_type == "wiki_markdown"
    assert wiki.markdown.startswith("# col-demo Wiki")
    assert "## Sources" in wiki.markdown
    assert result.metadata["synthesizer"] == "test.synthesizer"
    assert fake.requests[0].scope.scope_type == "collection"
    assert fake.requests[0].expert_context.startswith("Treat Atlas")


def test_concept_entity_wiki_returns_three_generic_standard_artifacts() -> None:
    generated = {
        "overview": "The reports describe projects and calibration.",
        "key_claims": ["Sensor A is used by Project Atlas."],
        "concepts": [
            {
                "name": "Thermal drift",
                "summary": "A calibration concern.",
                "evidence": "Thermal drift affects Sensor A",
                "source_file_id": "sha256-a",
            },
            {
                "name": "Invented concept",
                "summary": "Should be rejected.",
                "evidence": "This phrase is absent",
                "source_file_id": "sha256-a",
            },
        ],
        "entities": [
            {
                "name": "Project Atlas",
                "aliases": ["Atlas"],
                "entity_type": "experiment",
                "summary": "A named project in the report.",
                "evidence": "Project Atlas uses Sensor A",
                "source_file_id": "sha256-a",
                "location": "first sentence",
                "confidence": "high",
            }
        ],
        "caveats": ["Only two short reports were supplied."],
    }
    fake = FakeClient(f"```json\n{json.dumps(generated)}\n```")
    result = ConceptEntityWikiEnricher(lambda _url, _timeout: fake).enrich(request())

    assert [item.standard_data.artifact_type for item in result.artifacts] == [
        "wiki_markdown",
        "entity_list",
        "table",
    ]
    assert result.metadata["concept_count"] == 1
    assert result.metadata["entity_count"] == 1
    assert result.artifacts[1].standard_data.entities[0].name == "Project Atlas"
    assert result.artifacts[2].standard_data.rows[0]["name"] == "Thermal drift"
    assert any("Invented concept" in warning for warning in result.warnings)


def test_each_processor_has_independent_live_api_docs() -> None:
    for app, expected_name in (
        (readable_app, "toolbox.readable-wiki"),
        (concept_entity_app, "toolbox.concept-entity-wiki"),
    ):
        client = TestClient(app)
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/v1/descriptor").json()["name"] == expected_name
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/v1/enrich" in schema.json()["paths"]
