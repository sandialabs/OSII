# %% [markdown]
# # 05 — Build and search the local lexical index
#
# Lexical search is fully local. It turns the extracted text into derived
# chunks and a BM25 index; no embedding or model service is required.

# %%
from osii.domain.services.search import dashboard_search
from osii.search.lexical import build_bm25_index

from _demo_support import demo_paths

# %%
_, _, OSII_ROOT = demo_paths()
index_path, metadata_path = build_bm25_index(OSII_ROOT)
mode, results = dashboard_search(
    OSII_ROOT,
    query="calibration drift",
    mode="lexical",
    top_k=5,
)

print("Index:", index_path)
print("Metadata:", metadata_path)
print("Mode:", mode)
for result in results:
    print(f"- {result['source_relpath']}: {result['snippet']}")
