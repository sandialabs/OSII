# %% [markdown]
# # 04 — Make retrieval useful before adding a model
#
# Agentic systems need retrieval, but retrieval does not have to begin with an
# embedding service. BM25 gives OSII a dependable local baseline for exact
# terminology, identifiers, names, and phrases. It works offline and provides a
# reference point for evaluating more complex methods.
#
# Most importantly, the index is not canonical. It can be deleted, tuned, and
# rebuilt from preferred text while object identity and provenance stay stable.

# %%
from osii.domain.scopes.collections import list_collections
from osii.domain.services.search import dashboard_search
from osii.search.lexical import build_bm25_index

from _demo_support import demo_paths, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the extraction example first.")

# %% [markdown]
# ## Build a derived index
#
# Chunking creates retrieval-sized views over preferred object text. Those
# chunks keep character offsets back into the object, so a good match can return
# to evidence rather than becoming an orphaned string in a vector database.

# %%
index_path, metadata_path = build_bm25_index(paths.osii_root)

print("BM25 index:", index_path)
print("Chunk metadata:", metadata_path)

# %% [markdown]
# ## State a research question as an ordinary query
#
# Keeping the query in its own cell makes adaptation obvious. Replace it with
# the language used in your own corpus and compare results before changing the
# retrieval algorithm.

# %%
ROOT_QUERY = "low Reynolds number viscosity swimming microorganisms"

print(ROOT_QUERY)

# %% [markdown]
# ## Search the complete library

# %%
mode_used, root_results = dashboard_search(
    paths.osii_root,
    query=ROOT_QUERY,
    mode="lexical",
    top_k=5,
    scope={"scope_type": "root"},
)

print("Mode used:", mode_used)
print("Results:", len(root_results))

# %% [markdown]
# ## Inspect grounding, not only scores
#
# A score ranks candidates. Object ID, source path, and character offsets make
# the candidate defensible. An agent should carry both ranking and grounding
# forward when producing an answer or deciding on another tool call.

# %%
for result in root_results:
    print(f"- {result['source_relpath']}  score={result['score']:.3f}")
    print(f"  {result['snippet']}")
    print(f"  chars={result.get('char_start')}:{result.get('char_end')}")

# %% [markdown]
# ## Reuse retrieval inside a task-specific scope
#
# The search implementation stays the same; only the explicit context changes.
# This is why scopes are useful building blocks for future agents.

# %%
collection = next(
    item for item in list_collections(paths.osii_root)
    if item["name"] == "Purcell analysis"
)
collection_scope = {
    "scope_type": "collection",
    "collection_id": collection["id"],
}

COLLECTION_QUERY = "scallop theorem reciprocal motion"

# %%
_, collection_results = dashboard_search(
    paths.osii_root,
    query=COLLECTION_QUERY,
    mode="lexical",
    top_k=5,
    scope=collection_scope,
)

for result in collection_results:
    print(f"- {result['source_relpath']}")
    print(f"  {result['snippet']}")

# %% [markdown]
# Lexical retrieval remains available when every optional model endpoint is
# offline. That is both a usability guarantee and a research control: later
# hybrid results can be compared against a transparent zero-model baseline.
