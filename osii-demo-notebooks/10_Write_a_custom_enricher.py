# %% [markdown]
# # 10 — Write a standard-artifact enricher
#
# Enrichers are where domain expertise becomes reusable structured knowledge.
# They operate over existing text and return tables, entity lists, knowledge
# graphs, or wiki Markdown. A standard artifact can be rendered by the OSII
# dashboard and consumed by an agent without custom integration code.

# %% [markdown]
# ## Import one public artifact family
#
# This example builds an entity list. The same pattern applies to the SDK's
# table, graph, and wiki types.

# %%
import re

from osii_processor_sdk import (
    Artifact,
    Capability,
    DocumentInput,
    Enricher,
    EnrichmentRequest,
    EnrichmentResponse,
    Entity,
    EntityListArtifactData,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    ScopeInput,
    create_processor_app,
)

# %% [markdown]
# ## Describe a domain product, not a UI component
#
# `output_kinds=["entity_list"]` tells consumers how to handle the result. A
# processor can improve its algorithm without requiring a new dashboard page.

# %%
ENTITY_ENRICHER = ProcessorDescriptor(
    name="demo.capitalized-entities",
    version="1.0.0",
    display_name="Capitalized Entity Candidate Enricher",
    description="Finds grounded capitalized phrases and returns a standard entity list.",
    kind=ProcessorKind.ENRICHER,
    capabilities=Capability(
        scope_types=["object", "folder", "collection", "root"],
        output_kinds=["entity_list"],
    ),
    config_schema={
        "type": "object",
        "properties": {
            "minimum_characters": {
                "type": "integer",
                "title": "Minimum entity length",
                "minimum": 2,
                "default": 3,
            }
        },
        "additionalProperties": False,
    },
)

print(ENTITY_ENRICHER.model_dump())

# %% [markdown]
# ## Separate candidate detection from the service boundary

# %%
ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*\b")


def find_candidates(document, minimum_characters):
    text = document.text or ""
    for match in ENTITY_PATTERN.finditer(text):
        if len(match.group()) >= minimum_characters:
            yield match

# %% [markdown]
# ## Return a standard artifact with narrow provenance

# %%
class CapitalizedEntityEnricher(Enricher):
    descriptor = ENTITY_ENRICHER

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        minimum = int(request.config.get("minimum_characters", 3))
        by_name = {}

        for document in request.scope.documents:
            for match in find_candidates(document, minimum):
                by_name.setdefault(match.group(), []).append(
                    ProvenanceRef(
                        file_id=document.file_id,
                        char_start=match.start(),
                        char_end=match.end(),
                    )
                )

        entities = [
            Entity(
                id=f"entity-{index}",
                name=name,
                entity_type="candidate",
                mentions=mentions,
            )
            for index, (name, mentions) in enumerate(sorted(by_name.items()), start=1)
        ]

        artifact = Artifact(
            id="capitalized-entities",
            kind="entities",
            media_type="application/json",
            standard_data=EntityListArtifactData(
                title="Capitalized entity candidates",
                description="Grounded candidates for domain review.",
                entities=entities,
            ),
        )

        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[artifact],
        )

# %% [markdown]
# ## Test with a tiny representative scope

# %%
scope = ScopeInput(
    scope_type="collection",
    scope_id="demo-collection",
    documents=[
        DocumentInput(
            file_id="object-purcell",
            filename="purcell.txt",
            text=(
                "Edward Purcell described Life at Low Reynolds Number for an "
                "audience at the American Physical Society."
            ),
        )
    ],
)

request = EnrichmentRequest(
    request_id="demo-enrichment-1",
    scope=scope,
    expert_context="Candidates will be reviewed by a fluid-dynamics researcher.",
    config={"minimum_characters": 3},
)

# %%
enricher = CapitalizedEntityEnricher()
response = enricher.enrich(request)
artifact_data = response.artifacts[0].standard_data

for entity in artifact_data.entities:
    print(entity.name, "->", [mention.model_dump() for mention in entity.mentions])

# %%
assert response.request_id == request.request_id
assert response.artifacts[0].standard_data.artifact_type == "entity_list"
assert all(entity.mentions for entity in artifact_data.entities)

print("Standard artifact checks passed.")

# %% [markdown]
# ## Expose it through the generated service

# %%
app = create_processor_app(enricher)

print("Generated routes:")
for route in app.routes:
    if getattr(route, "path", "").startswith(("/health", "/v1")):
        print("-", route.path)

# %% [markdown]
# This toy capitalization rule is not the point; the replaceable boundary is.
# Substitute an ontology matcher, scientific parser, local model, or approved
# remote service. If the processor returns a validated standard artifact with
# defensible provenance, OSII can carry that research result into dashboards,
# packages, APIs, and agent workflows without changing the core.
