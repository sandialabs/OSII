# %% [markdown]
# # 00 — Start with the architecture, not the machinery
#
# OSII is an intelligence **sidecar** for files. The originals remain where a
# person put them; OSII records grounded text, provenance, scopes, and derived
# knowledge beside them. This matters because source documents should outlive
# today's OCR engine, vector database, model provider, and user interface.
#
# This first example creates the smallest useful OSII store and then inspects
# what was written. No service, container, network connection, or model is
# required.

# %% [markdown]
# ## A mental model for the whole series
#
# Every later example fits into this flow:
#
# ```text
# source files
#     |
#     v
# extractor  ---> canonical text + provenance
#     |                    |
#     |                    +--> search indexes (rebuildable)
#     |                    +--> synthesis (derived)
#     |                    +--> enrichments (derived)
#     v
# OSII core validates and commits the portable sidecar
#     |
#     +--> Python / REST / dashboard / MCP / agent workflows
# ```
#
# Processors compute. OSII core persists. Consumers share the same objects,
# scopes, and artifacts. That separation is the main architectural idea.

# %% [markdown]
# ## Find the source documents
#
# The path below is the one value most users change. The bundled Purcell PDF
# makes the walkthrough runnable immediately; you can add your own files to the
# same directory.

# %%
from pathlib import Path

DOCUMENTS_DIR = Path("demo-workspace/documents")

# %%
documents = sorted(path for path in DOCUMENTS_DIR.rglob("*") if path.is_file())

if not documents:
    raise RuntimeError(f"No documents found in {DOCUMENTS_DIR.resolve()}")

print(f"Found {len(documents)} source document(s):")
for document in documents:
    print("-", document.relative_to(DOCUMENTS_DIR))

# %% [markdown]
# The code above only reads paths. OSII has not changed or copied an original.
# This read-only relationship is useful for research collections and controlled
# data: deleting a derived index should never delete the evidence it describes.

# %% [markdown]
# ## Choose where the sidecar lives
#
# A sidecar is portable because it is an ordinary directory, not a connection
# to a particular database service. Keeping it beside the demonstration files
# also makes the source/derived boundary visible while learning.

# %%
documents_dir = DOCUMENTS_DIR.resolve()
workspace = Path("demo-workspace").resolve()
osii_root = workspace / ".osii"
exports_dir = workspace / "exports"

exports_dir.mkdir(parents=True, exist_ok=True)

print("Originals:", documents_dir)
print("Sidecar:  ", osii_root)

# %% [markdown]
# ## Initialize canonical storage
#
# The `osii` package contains the core implementation. At this research stage,
# its Python API is organized into focused modules rather than one large
# convenience object. These imports make each responsibility visible:
#
# - storage creates the portable layout;
# - folder identity gives the root scope a stable ID;
# - the root descriptor records how this store relates to its source;
# - the catalog is a rebuildable read accelerator.

# %%
from osii.domain.catalog_db import rebuild_catalog, verify_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.store import ensure_osii_store_layout

# %%
layout = ensure_osii_store_layout(osii_root)
root_folder_id = get_or_create_folder_id(osii_root, "")

print("Root folder ID:", root_folder_id)
print("Canonical areas:")
for name, path in layout.items():
    print(f"- {name}: {path.relative_to(osii_root)}")

# %% [markdown]
# ## Describe the relationship to the source
#
# `root.toml` is small on purpose. A person can inspect it without OSII, and a
# future agent can understand which corpus a store describes without guessing
# from a machine-specific folder layout.

# %%
write_root_toml(
    osii_root,
    root_folder_id=root_folder_id,
    host_path=str(documents_dir),
    container_path="/data/source",
    notes="OSII Python demonstration",
    tool_versions={"demo_walkthrough": "1"},
)

root_descriptor = osii_root / "root.toml"
print(root_descriptor.read_text(encoding="utf-8"))

# %% [markdown]
# ## Build the disposable catalog
#
# SQLite makes repeated reads fast, but it is not the authority. Rebuilding it
# from the sidecar is a deliberate test of that design: performance state can
# be replaced without losing the library's meaning.

# %%
catalog_status = rebuild_catalog(osii_root)

print("Catalog build:", catalog_status)
print("Catalog verification:", verify_catalog(osii_root))

# %% [markdown]
# ## Pause and inspect
#
# Open `demo-workspace/.osii/` in your file browser. At this point you should be
# able to answer three questions:
#
# 1. Where are the untouched originals?
# 2. Where will OSII put canonical and derived information?
# 3. Which database can be deleted and rebuilt?
#
# Continue with the local Tesseract extraction notebook. Every supported
# extractor ultimately commits the same OSII object structure; downstream code
# does not need to care which implementation produced it.
