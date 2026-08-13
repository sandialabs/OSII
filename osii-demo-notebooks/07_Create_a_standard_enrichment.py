# %% [markdown]
# # 07 — Create standard knowledge products
#
# Enrichment derives optional products from preferred extracted text. These two
# model-free examples produce standard artifacts:
#
# - a table of frequency-ranked, lemmatized noun/adjective 2–4-grams;
# - a grounded entity-candidate list with source mentions.
#
# Standard table, entity-list, knowledge-graph, and wiki-Markdown artifacts can
# be rendered by the dashboard and consumed by agents without custom UI code.

# %%
import json

from osii.domain.artifacts.read_enrichments import list_scope_enrichments
from osii.domain.scopes.collections import list_collections
from osii.enrichment.linguistic_examples import (
    EntityCandidateEnricher,
    NounAdjectiveNgramEnricher,
)

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "objects", "Run scripts 00–02 first.")

root_scope = {"scope_type": "root"}
collection = next(
    item for item in list_collections(paths.osii_root) if item["name"] == "Calibration evidence"
)
collection_scope = {"scope_type": "collection", "collection_id": collection["id"]}

keyword_result = NounAdjectiveNgramEnricher().enrich(
    osii_store=paths.osii_root,
    scope=root_scope,
    expert_context="Experiment names and measurement terms are meaningful.",
    enricher_config={"top_k": 20},
)
entity_result = EntityCandidateEnricher().enrich(
    osii_store=paths.osii_root,
    scope=collection_scope,
    enricher_config={"top_k": 20},
)

heading("Committed enrichment results")
print("Keywords:", keyword_result["result"])
print("Entities:", entity_result["result"])

# %% [markdown]
# ## Read the artifacts back through the same generic interface as the API

# %%
def show_artifacts(scope: dict) -> None:
    for artifact in list_scope_enrichments(paths.osii_root, scope):
        if artifact["name"].endswith(".meta.json"):
            continue
        artifact_path = paths.osii_root / artifact["relpath"]
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        print(
            f"- {payload.get('artifact_type')}: {payload.get('title')} "
            f"({artifact_path.relative_to(paths.osii_root)})"
        )
        if payload.get("rows"):
            print("  first rows:", payload["rows"][:3])
        if payload.get("entities"):
            print("  first entities:", [item["name"] for item in payload["entities"][:5]])


heading("Root artifacts")
show_artifacts(root_scope)
heading("Collection artifacts")
show_artifacts(collection_scope)

# %% [markdown]
# An SME processor can return any of the same standard schemas. OSII core owns
# persistence, and the frontend remains generic. Model-backed wiki Markdown is
# demonstrated next as an explicitly optional enhancement.
