"""Minimal entity-list enricher."""

import re

from osii_processor_sdk import (
    Artifact,
    Capability,
    Enricher,
    EnrichmentRequest,
    EnrichmentResponse,
    Entity,
    EntityListArtifactData,
    ProcessorDescriptor,
    ProcessorKind,
    create_processor_app,
)


class CapitalizedEntityEnricher(Enricher):
    descriptor = ProcessorDescriptor(
        name="example.capitalized-entities",
        version="1.0.0",
        display_name="Capitalized Entity Example",
        description="Finds capitalized phrases to demonstrate entity artifacts.",
        kind=ProcessorKind.ENRICHER,
        capabilities=Capability(
            scope_types=["object", "folder", "collection", "root"],
            output_kinds=["entity_list"],
        ),
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        names = set()
        for document in request.scope.documents:
            names.update(re.findall(r"\b[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*\b", document.text or ""))
        entities = [
            Entity(id=f"entity-{index}", name=name, entity_type="candidate")
            for index, name in enumerate(sorted(names), start=1)
        ]
        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[
                Artifact(
                    id="entities",
                    kind="entities",
                    media_type="application/json",
                    standard_data=EntityListArtifactData(
                        title="Candidate entities",
                        entities=entities,
                    ),
                )
            ],
        )


app = create_processor_app(CapitalizedEntityEnricher())

