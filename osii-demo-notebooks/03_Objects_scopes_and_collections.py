# This file is generated from the similarly named .ipynb notebook.
# Edit this Python companion for normal code changes; preserve the notebook as an artifact.

# %% [markdown]
# # Inspect Objects, Scopes, and Collections from Python
#
# This notebook explores the OSII backend directly through Python after an OSII store has already been built.
#
# The notebook demonstrates:
#
# - scope descriptors
# - folder and collection discovery
# - collection creation from a TOML file
# - object summaries
# - object aggregates
# - preferred text
# - artifact summaries
#
# The goal is to show how the backend can be inspected as a Python package, not only through the API.

# %%
from pathlib import Path
import json

# %% [markdown]
# ## Define paths
#
# This notebook assumes the OSII store has already been built.

# %%
REPO_ROOT = Path(r"C:\Users\hbkomko\OneDrive - Sandia National Laboratories\Documents\AI_tools\ai-ready-everything\ai-ready-ingest").resolve()
DATA_ROOT = REPO_ROOT / "data_volume" / "my_data"
OSII_ROOT = REPO_ROOT / "data_volume" / ".osii"
CONFIG_DIR = REPO_ROOT / "config"

REPO_ROOT, DATA_ROOT, OSII_ROOT, CONFIG_DIR

# %%
assert OSII_ROOT.exists(), f"OSII root not found: {OSII_ROOT}"
print("OSII root exists.")

# %% [markdown]
# ## Import Python helpers
#
# The backend organizes logic around:
#
# - read helpers
# - scope helpers
# - object summaries
# - collection import helpers

# %%
from osii.domain.read.catalog import load_files_catalog, load_folders_catalog
from osii.domain.read.root import get_root_descriptor
from osii.domain.read.docs import get_doc_meta, get_doc_overview
from osii.domain.read.manifest import list_manifest_records
from osii.domain.scopes.descriptors import describe_scope
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.collections import (
    list_collections,
    create_collection,
    get_collection,
    list_collection_documents,
    add_documents_to_collection,
)
from osii.domain.scopes.collection_files import (
    load_collection_definition,
    parse_collection_metadata,
    resolve_collection_members,
)
from osii.domain.artifacts.object_summaries import get_object_summary, get_object_summaries
from osii.domain.artifacts.object_artifacts import get_object_artifact_summary
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.artifacts.read_enrichments import list_scope_enrichments

# %% [markdown]
# ## Root descriptor
#
# The root descriptor identifies the current store and its source-data context.

# %%
root_descriptor = get_root_descriptor(OSII_ROOT)
root_descriptor

# %% [markdown]
# ## Folder scopes
#
# Folder scopes are structural scopes derived from the source hierarchy.
#
# The backend stores them as a flat catalog with paths, and clients can construct a tree from those paths if desired.

# %%
folders_catalog = load_folders_catalog(OSII_ROOT)
len(folders_catalog), folders_catalog[:10]

# %% [markdown]
# ## File catalog
#
# The file catalog maps source-relative files to stable object identifiers.

# %%
files_catalog = load_files_catalog(OSII_ROOT)
len(files_catalog), files_catalog[:10]

# %% [markdown]
# ## Describe the root scope
#
# The backend exposes scope semantics uniformly across root, folder, collection, and object scopes.

# %%
root_scope = {"scope_type": "root"}
root_scope_description = describe_scope(OSII_ROOT, root_scope)
root_scope_members = list_scope_file_ids(OSII_ROOT, root_scope)

root_scope_description, len(root_scope_members)

# %% [markdown]
# ## Describe one folder scope
#
# This shows how structural scope membership can be resolved directly from Python.

# %%
assert folders_catalog, "No folder scopes found."

sample_folder = folders_catalog[0]
folder_scope = {
    "scope_type": "folder",
    "folder_id": sample_folder["folder_id"],
}

folder_scope_description = describe_scope(OSII_ROOT, folder_scope)
folder_scope_members = list_scope_file_ids(OSII_ROOT, folder_scope)

folder_scope_description, len(folder_scope_members)

# %% [markdown]
# ## Create a collection from a TOML definition
#
# Collections are logical scopes independent of source folder structure.
#
# This example imports a collection definition from `config/my_collection.toml`.

# %%
collection_file = CONFIG_DIR / "my_collection.toml"
print(collection_file)
print()
print(collection_file.read_text(encoding="utf-8"))

# %%
collection_payload = load_collection_definition(collection_file)
collection_metadata = parse_collection_metadata(collection_payload)
collection_file_ids = resolve_collection_members(OSII_ROOT, collection_payload)

collection_metadata, collection_file_ids

# %% [markdown]
# ## Create or inspect the collection resource
#
# This notebook creates a collection directly through the Python domain helpers.
#
# If a collection with the same name already exists, you may want to skip creation or inspect existing collections first.

# %%
existing_collections = list_collections(OSII_ROOT)
existing_collections

# %%
matching = [c for c in existing_collections if c["name"] == collection_metadata["name"]]

if matching:
    created_collection = matching[0]
else:
    created_collection = create_collection(
        OSII_ROOT,
        name=collection_metadata["name"],
        description=collection_metadata["description"],
        kind=collection_metadata["kind"],
        color=collection_metadata["color"],
    )
    add_documents_to_collection(OSII_ROOT, created_collection["id"], collection_file_ids)

created_collection

# %% [markdown]
# ## Collection membership
#
# The collection resource now defines a logical scope over selected objects.

# %%
collection_members = list_collection_documents(OSII_ROOT, created_collection["id"])
collection_members

# %% [markdown]
# ## Resolve collection scope membership
#
# Collections participate in the same scope model as root, folders, and objects.

# %%
collection_scope = {
    "scope_type": "collection",
    "collection_id": created_collection["id"],
}

collection_scope_description = describe_scope(OSII_ROOT, collection_scope)
collection_scope_members = list_scope_file_ids(OSII_ROOT, collection_scope)

collection_scope_description, collection_scope_members

# %% [markdown]
# ## Object summaries
#
# Object summaries are the lightweight file-card payloads used for file-grid browsing and quick inspection.

# %%
object_summaries = get_object_summaries(OSII_ROOT, collection_scope_members)
object_summaries

# %% [markdown]
# ## Inspect one object summary
#
# This is the lightweight summary the dashboard would use for card/list rendering.

# %%
assert object_summaries, "No object summaries found."
sample_summary = object_summaries[0]
sample_summary

# %% [markdown]
# ## Inspect one object aggregate
#
# The full object aggregate includes richer metadata, processing information, and artifact summaries.

# %%
sample_file_id = sample_summary["file_id"]

sample_meta = get_doc_meta(OSII_ROOT, sample_file_id)
sample_overview = get_doc_overview(OSII_ROOT, sample_file_id)
sample_artifact_summary = get_object_artifact_summary(OSII_ROOT, sample_file_id)

sample_meta, sample_overview, sample_artifact_summary

# %% [markdown]
# ## Preferred text
#
# Preferred text is the backend's current reading/searching representation for an object.
#
# If edited text exists, it may become preferred. Otherwise canonical extracted text remains preferred.

# %%
preferred_text = get_preferred_text_representation(OSII_ROOT, sample_file_id)
preferred_text

# %% [markdown]
# ## Canonical manifest records
#
# Manifest records remain the canonical provenance structure for extracted object content.

# %%
sample_manifest = list_manifest_records(OSII_ROOT, sample_file_id)
sample_manifest[:10]

# %% [markdown]
# ## Enrichments for one object
#
# Enrichments are optional, rebuildable derived artifacts such as keywords or wiki bundles.

# %%
object_enrichments = list_scope_enrichments(
    OSII_ROOT,
    {"scope_type": "object", "file_id": sample_file_id},
)
object_enrichments

# %% [markdown]
# ## Enrichments for the collection scope
#
# Collections may also own enrichments independently of the source folder hierarchy.

# %%
collection_enrichments = list_scope_enrichments(OSII_ROOT, collection_scope)
collection_enrichments

# %% [markdown]
# ## Summary
#
# This notebook demonstrated:
#
# - root, folder, and collection scope inspection
# - collection creation from a TOML file
# - lightweight object summaries
# - full object metadata and artifact summaries
# - preferred text inspection
# - enrichment discovery
#
# The next notebook will demonstrate derived processing:
#
# - synthesis
# - enrichment
# - search index build

# %%


# %%


# %%


