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
