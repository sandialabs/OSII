# %% [markdown]
# # 06 — Build local embeddings
#
# The guaranteed local hashing service requires no model download. This script calls the
# `EmbeddingClient` capability through its OpenAI-compatible `/v1/embeddings`
# endpoint and writes a FAISS index beside the lexical artifacts.

# %%
import os

from osii.indexing.common import embed_collection_resumable, get_embedding_model

from _demo_support import demo_paths

# %%
_, _, OSII_ROOT = demo_paths()

# In the Compose network, OSII already sets this to http://embeddings:8085/v1.
# For a host-run notebook, expose the service and use the host URL instead.
os.environ.setdefault("OSII_EMBEDDING_BASE_URL", "http://localhost:8085/v1")
model = get_embedding_model()

index_path, mapping_path, metadata_path = embed_collection_resumable(
    OSII_ROOT,
    model=model,
    batch_size=8,
)
print("Vector index:", index_path)
print("Mapping:", mapping_path)
print("Metadata:", metadata_path)
