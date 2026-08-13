# %% [markdown]
# # 06 — Add deterministic local hashing vectors
#
# `local.hashing` maps tokens and adjacent word pairs into normalized 384-D
# vectors. It is useful for testing vector plumbing and approximate lexical
# similarity, but it does not understand synonyms like a semantic model.
#
# Start it with `make dev-embedder` or
# `.\scripts\osii.ps1 dev-embedder`. If it is offline, this example skips
# cleanly. Changing to Ollama later creates a separate incompatible index.

# %%
from __future__ import annotations

import os
import tomllib

from _demo_support import demo_paths, get_json, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "objects", "Run scripts 00–02 first.")

HASHING_URL = "http://127.0.0.1:8085"
descriptor = get_json(f"{HASHING_URL}/v1/descriptor")

if descriptor is None:
    print(
        "The local hashing embedder is not running. Start `make dev-embedder` "
        "or `.\\scripts\\osii.ps1 dev-embedder`, then rerun this file."
    )
else:
    # These settings are scoped to this Python process. They make the selected
    # vector space explicit rather than inheriting an Ollama choice from Tools.
    os.environ["OSII_ROOT"] = str(paths.osii_root)
    os.environ["OSII_DEFAULT_EMBEDDER"] = "local.hashing"
    os.environ["EMBEDDING_MODEL"] = "osii-local-hashing-v1"
    configured = [url for url in os.environ.get("OSII_PROCESSORS", "").split(",") if url]
    if HASHING_URL not in configured:
        configured.append(HASHING_URL)
    os.environ["OSII_PROCESSORS"] = ",".join(configured)

    # Import after configuration so the client resolves this exact processor.
    from osii.domain.services.search import dashboard_search
    from osii.indexing.common import embed_collection_resumable

    heading(f"Connected to {descriptor['display_name']}")
    print(descriptor["description"])

    index_path, mapping_path, metadata_path = embed_collection_resumable(
        paths.osii_root,
        model="osii-local-hashing-v1",
        batch_size=8,
    )
    metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))

    heading("Vector index identity")
    print("Index:", index_path)
    print("Mapping:", mapping_path)
    print("Provider/model metadata:", metadata["embeddings"])

    mode_used, results = dashboard_search(
        paths.osii_root,
        query="calibration chamber drift",
        mode="hybrid",
        top_k=5,
        scope={"scope_type": "root"},
    )
    heading(f"Hybrid search ({mode_used})")
    for result in results:
        print("-", result["source_relpath"], "->", result["snippet"])

# %% [markdown]
# When using Ollama or a corporate embedder, keep the provider, model, digest,
# dimensions, normalization, and chunking identity together. OSII never mixes
# two vector spaces inside one FAISS index; BM25 stays usable during rebuilds.
