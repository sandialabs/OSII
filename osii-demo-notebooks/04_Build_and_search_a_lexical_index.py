# %% [markdown]
# # 05 — Build and search the local lexical index
#
# BM25 is OSII's zero-model retrieval baseline. It creates overlapping,
# provenance-aware chunks from preferred text, then ranks exact and related
# word matches. No model service, network access, or container is required.

# %%
from osii.domain.scopes.collections import list_collections
from osii.domain.services.search import dashboard_search
from osii.search.lexical import build_bm25_index

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "objects", "Run scripts 00–02 first.")

index_path, metadata_path = build_bm25_index(paths.osii_root)

heading("Index files")
print("BM25 index:", index_path)
print("Metadata:", metadata_path)

# %% [markdown]
# ## Search the complete library
#
# Search results retain object, segment, page when available, and character
# offsets so the dashboard or an agent can return to the evidence.

# %%
mode_used, results = dashboard_search(
    paths.osii_root,
    query="low Reynolds number viscosity swimming microorganisms",
    mode="lexical",
    top_k=5,
    scope={"scope_type": "root"},
)

heading(f"Root results ({mode_used})")
for result in results:
    print(f"- {result['source_relpath']}  score={result['score']:.3f}")
    print(f"  {result['snippet']}")
    print(f"  chars={result.get('char_start')}:{result.get('char_end')}")

# %% [markdown]
# ## Run the same search inside a collection

# %%
collection = next(
    item for item in list_collections(paths.osii_root) if item["name"] == "Purcell analysis"
)
_, collection_results = dashboard_search(
    paths.osii_root,
    query="scallop theorem reciprocal motion",
    mode="lexical",
    top_k=5,
    scope={"scope_type": "collection", "collection_id": collection["id"]},
)

heading("Collection-scoped results")
for result in collection_results:
    print("-", result["source_relpath"], "->", result["snippet"])

# %% [markdown]
# Lexical retrieval remains available even if every optional embedding or LLM
# endpoint is offline. The next script adds the deterministic hashing-vector
# baseline without claiming that those vectors are semantic.
