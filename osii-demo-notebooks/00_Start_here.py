# %% [markdown]
# # Start here: point OSII at your documents
#
# Put documents in `demo-workspace/documents`. It sits beside `.osii`, making
# the boundary between originals and OSII's derived sidecar easy to inspect.
# The bundled `purcell.pdf` makes the walkthrough runnable immediately. OSII
# reads source documents in place and never changes them.

# %%
from pathlib import Path

DOCUMENTS_DIR = Path("demo-workspace/documents")

documents = sorted(path for path in DOCUMENTS_DIR.rglob("*") if path.is_file())
if not documents:
    raise RuntimeError(f"No documents found in {DOCUMENTS_DIR.resolve()}")

print(f"Found {len(documents)} document(s):")
for document in documents:
    print("-", document.relative_to(DOCUMENTS_DIR))

# %% [markdown]
# ## Create the OSII sidecar
#
# The `.osii` directory holds portable text, provenance, collections, and
# knowledge products derived from the source documents. SQLite is only a
# rebuildable read catalog; the ordinary sidecar files remain authoritative.

# %%
from osii.domain.catalog_db import rebuild_catalog, verify_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.store import ensure_osii_store_layout


documents_dir = DOCUMENTS_DIR.resolve()
osii_root = Path("demo-workspace/.osii").resolve()
Path("demo-workspace/exports").mkdir(parents=True, exist_ok=True)

layout = ensure_osii_store_layout(osii_root)
root_folder_id = get_or_create_folder_id(osii_root, "")
write_root_toml(
    osii_root,
    root_folder_id=root_folder_id,
    host_path=str(documents_dir),
    container_path="/data/source",
    notes="OSII Python demonstration",
    tool_versions={"demo_walkthrough": "1"},
)
catalog_status = rebuild_catalog(osii_root)

print("OSII store:", osii_root)
print("Canonical directories:", ", ".join(layout))
print("Catalog build:", catalog_status)
print("Catalog verification:", verify_catalog(osii_root))

# %% [markdown]
# The source documents are still in `demo-workspace/documents/`. Everything
# OSII created is beside them under `demo-workspace/.osii/`, where you can
# inspect the TOML, JSONL, and text files directly. Continue with either
# extraction notebook: local Tesseract or corporate Shirty Textract.
