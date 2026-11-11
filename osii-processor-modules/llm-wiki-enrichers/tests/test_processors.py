from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from osii.processor_sdk import (
    DocumentInput,
    EnrichmentRequest,
    ScopeInput,
)
from wiki_enrichers.main import concept_entity_app, readable_app
from wiki_enrichers.processors import ConceptEntityWikiEnricher, ReadableWikiEnricher


class FakeClient:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.markdown))],
            model="actual-test-model",
            model_extra={"osii": {"connection": "top", "provider_type": "test"}},
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
    result = ReadableWikiEnricher().enrich(request(), client=fake, model="top")

    wiki = result.artifacts[0].standard_data
    assert wiki.artifact_type == "wiki_markdown"
    assert wiki.markdown.startswith("# col-demo Wiki")
    assert "## Sources" in wiki.markdown
    assert result.metadata["model_connection"] == "top"
    assert result.metadata["model"] == "actual-test-model"
    assert fake.requests[0]["model"] == "top"
    assert "Treat Atlas" in fake.requests[0]["messages"][1]["content"]


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
    result = ConceptEntityWikiEnricher().enrich(request(), client=fake, model="mid")

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
        assert client.post("/v1/enrich", json=request().model_dump(mode="json")).status_code == 422


def test_core_scope_batch_preserves_unequal_document_lengths():
    first="Complete source text " * 2000
    batch=EnrichmentRequest(request_id="batch-test",scope=ScopeInput(scope_type="root",scope_id="root",documents=[
        DocumentInput(file_id="long",filename="long.txt",text=first),
        DocumentInput(file_id="short",filename="short.txt",text="Short text")],metadata={"scope_batch":{"phase":"map"}}))
    client=FakeClient("# Combined wiki")
    response=ReadableWikiEnricher().enrich(batch,client=client,model="test")
    assert response.metadata["input_truncated"] is False
    assert first in str(client.requests)
    batch.config["max_input_chars"]=4000
    import pytest
    with pytest.raises(ValueError,match="Scope batch exceeds"):
        ReadableWikiEnricher().enrich(batch,client=client,model="test")
    assert len(client.requests)==1
