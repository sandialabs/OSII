# %% [markdown]
# # 06 — Add domain knowledge without changing the evidence
#
# Enrichment creates optional, rebuildable knowledge products over grounded
# text. It is the natural extension point when a subject-matter expert wants to
# identify entities, normalize measurements, build a results table, connect a
# knowledge graph, or write a wiki—without redefining canonical extraction.
#
# A useful rule of thumb:
#
# - if the output says what the source **contains**, it may be extraction;
# - if it explains the source in prose, it is synthesis;
# - if it adds a parallel analytical structure, it is enrichment.

# %% [markdown]
# ## Why standard artifacts matter
#
# A processor-specific JSON blob forces every UI and agent to learn custom
# code. OSII instead defines standard table, entity-list, knowledge-graph, and
# wiki-Markdown schemas. Domain algorithms remain open-ended while consumers
# receive predictable shapes.
#
# This is how a research prototype becomes a building block: a new enricher can
# produce a result that the dashboard and an agent already know how to inspect.

# %%
import json

from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.scopes.collections import list_collections
from osii.enrichment.linguistic_examples import (
    EntityCandidateEnricher,
    NounAdjectiveNgramEnricher,
)

from _demo_support import demo_paths, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the extraction example first.")

root_scope = {"scope_type": "root"}
collection = next(
    item for item in list_collections(paths.osii_root)
    if item["name"] == "Purcell analysis"
)
collection_scope = {
    "scope_type": "collection",
    "collection_id": collection["id"],
}

print("Root scope:", root_scope)
print("Collection scope:", collection_scope)

# %% [markdown]
# ## Enrichment 1: a keyword table
#
# This model-free example ranks lemmatized noun/adjective phrases. The domain
# context describes which details are meaningful; `top_k` bounds the output.

# %%
keyword_enricher = NounAdjectiveNgramEnricher()

keyword_result = keyword_enricher.enrich(
    osii_store=paths.osii_root,
    scope=root_scope,
    expert_context=(
        "Physical concepts, organism names, equations, and dimensional "
        "quantities are meaningful."
    ),
    enricher_config={"top_k": 20},
)

print(keyword_result["result"])

# %% [markdown]
# ## Enrichment 2: grounded entity candidates
#
# This example targets a collection rather than the whole root. Mentions retain
# provenance so a person or agent can verify why an entity was proposed.

# %%
entity_enricher = EntityCandidateEnricher()

entity_result = entity_enricher.enrich(
    osii_store=paths.osii_root,
    scope=collection_scope,
    enricher_config={"top_k": 20},
)

print(entity_result["result"])

# %% [markdown]
# ## List artifacts without knowing their producer
#
# Generic discovery is the payoff of standardization. The reader asks for
# artifacts on a scope; it does not import either enrichment algorithm.

# %%
root_artifacts = list_scope_enrichments(paths.osii_root, root_scope)
collection_artifacts = list_scope_enrichments(paths.osii_root, collection_scope)

print("Root artifacts:", len(root_artifacts))
print("Collection artifacts:", len(collection_artifacts))

# %% [markdown]
# ## Inspect standard payloads

# %%
def load_standard_payload(artifact):
    artifact_path = paths.osii_root / artifact["relpath"]
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact_path, payload


def show_artifact(artifact):
    artifact_path, payload = load_standard_payload(artifact)
    print(f"- {payload.get('artifact_type')}: {payload.get('title')}")
    print(f"  path: {artifact_path.relative_to(paths.osii_root)}")
    if payload.get("rows"):
        print("  first rows:", payload["rows"][:3])
    if payload.get("entities"):
        names = [item["name"] for item in payload["entities"][:5]]
        print("  first entities:", names)

# %%
print("Root-scope standard artifacts")
for artifact in root_artifacts:
    if not artifact["name"].endswith(".meta.json"):
        show_artifact(artifact)

# %%
print("Collection-scope standard artifacts")
for artifact in collection_artifacts:
    if not artifact["name"].endswith(".meta.json"):
        show_artifact(artifact)

# %% [markdown]
# Your own SME processor can return these same standard schemas. OSII core owns
# persistence and lineage; the processor owns the research method. Step 10
# builds a small custom enricher using only the public Processor SDK.
