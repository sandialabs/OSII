# %% [markdown]
# # 05 — Add a vector space without surrendering the architecture
#
# Embeddings are one replaceable representation of text. They can improve
# retrieval, but they should not become the only record of what a document said
# or which model produced a result.
#
# This example uses `local.hashing`, a deterministic 384-dimensional baseline.
# It exercises vector indexing without a model download. It is useful for
# plumbing and approximate lexical similarity; it does **not** understand
# language like a semantic model.

# %% [markdown]
# ## Why vector identity matters
#
# Vectors are only comparable inside the same space. Provider, model, digest,
# dimensions, normalization, and chunking settings therefore belong with the
# index. OSII records them so a workflow cannot silently mix incompatible
# vectors after a model change.
#
# Start the normal stack from the repository root:
#
# ```bash
# make dev
# ```

# %%
from __future__ import annotations

import os
import tomllib

from _demo_support import demo_paths, get_json, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the extraction example first.")

HASHING_URL = "http://127.0.0.1:8085"
descriptor = get_json(f"{HASHING_URL}/v1/descriptor")

print(descriptor or "Local hashing embedder is offline.")

# %% [markdown]
# ## Make the processor choice explicit
#
# These values are scoped to this notebook process. Explicit configuration is
# preferable to accidentally inheriting whichever model a UI used last.

# %%
if descriptor:
    os.environ["OSII_ROOT"] = str(paths.osii_root)
    os.environ["OSII_DEFAULT_EMBEDDER"] = "local.hashing"
    os.environ["EMBEDDING_MODEL"] = "osii-local-hashing-v1"

    processor_urls = [
        url for url in os.environ.get("OSII_PROCESSORS", "").split(",") if url
    ]
    if HASHING_URL not in processor_urls:
        processor_urls.append(HASHING_URL)
    os.environ["OSII_PROCESSORS"] = ",".join(processor_urls)

    print("Embedder:", os.environ["OSII_DEFAULT_EMBEDDER"])
    print("Model identity:", os.environ["EMBEDDING_MODEL"])
else:
    print("Start the embedder service, then rerun this cell.")

# %% [markdown]
# ## Import the configured indexing workflow
#
# The import happens after configuration because the client resolves the
# selected processor. Keeping this in a separate cell makes the dependency
# visible rather than burying it inside index construction.

# %%
if descriptor:
    from osii.domain.services.search import dashboard_search
    from osii.indexing.common import embed_collection_resumable

# %% [markdown]
# ## Build a resumable derived index

# %%
if descriptor:
    index_path, mapping_path, metadata_path = embed_collection_resumable(
        paths.osii_root,
        model="osii-local-hashing-v1",
        batch_size=8,
    )

    print("Vector index:", index_path)
    print("Object/chunk mapping:", mapping_path)
    print("Metadata:", metadata_path)

# %% [markdown]
# ## Inspect the vector-space identity
#
# This metadata is what makes the index scientifically interpretable and safe
# to rebuild. A bare array of floats is not enough provenance.

# %%
if descriptor:
    metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
    print(metadata["embeddings"])

# %% [markdown]
# ## Ask for hybrid retrieval
#
# Hybrid search combines lexical evidence with the configured vector index.
# BM25 remains available as a fallback while a vector space is offline or being
# rebuilt.

# %%
HYBRID_QUERY = "viscosity and reciprocal swimming motion"

if descriptor:
    mode_used, results = dashboard_search(
        paths.osii_root,
        query=HYBRID_QUERY,
        mode="hybrid",
        top_k=5,
        scope={"scope_type": "root"},
    )

    print("Mode used:", mode_used)
    for result in results:
        print(f"- {result['source_relpath']}")
        print(f"  {result['snippet']}")

# %% [markdown]
# To substitute Ollama or a corporate embedder, change the processor and model
# identity, then build a separate index. The OSII object and scope APIs do not
# change. This is the recurring pattern: stable grounded resources underneath,
# replaceable research methods above.
