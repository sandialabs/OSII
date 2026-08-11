from io import BytesIO
import urllib.error

import pytest
from pydantic import ValidationError

from osii_processor_sdk import (
    Artifact,
    DocumentInput,
    KnowledgeGraphArtifactData,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    EnrichmentRequest,
    ScopeInput,
    TableArtifactData,
    TableColumn,
)
from osii_processor_sdk.client import ProcessorClient, ProcessorClientError


def test_processor_client_preserves_http_error_body(monkeypatch):
    error = urllib.error.HTTPError(
        "http://processor/v1/embed",
        422,
        "Unprocessable Entity",
        {},
        BytesIO(b'{"detail":"input length exceeds context length"}'),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(ProcessorClientError, match="exceeds context length"):
        ProcessorClient("http://processor")._post("/v1/embed", "{}")


def test_enrichment_request_requires_scope():
    request = EnrichmentRequest(
        request_id="request-1",
        scope=ScopeInput(
            scope_type="object",
            scope_id="file-1",
            documents=[DocumentInput(filename="report.pdf")],
        ),
    )
    assert request.api_version == "v1"


def test_artifact_requires_one_payload():
    with pytest.raises(ValidationError):
        Artifact(id="a1", kind="table", media_type="application/json")


def test_table_requires_unique_columns():
    with pytest.raises(ValidationError):
        TableArtifactData(
            title="Bad table",
            columns=[
                TableColumn(key="value", label="First"),
                TableColumn(key="value", label="Second"),
            ],
            rows=[],
        )


def test_graph_edges_reference_nodes():
    with pytest.raises(ValidationError):
        KnowledgeGraphArtifactData(
            title="Bad graph",
            nodes=[KnowledgeGraphNode(id="a", label="A", entity_type="thing")],
            edges=[
                KnowledgeGraphEdge(
                    id="edge-1",
                    source="a",
                    target="missing",
                    relation="references",
                )
            ],
        )
