# %% [markdown]
# # 03 — Browse scopes, create a collection, and add governance metadata
#
# A folder is structural; a collection is a user-defined logical grouping.
# Both resolve to stable object IDs. Governance labels, handling notes, and
# plain-text tags travel with object sidecars, but they are metadata—not access
# control.

# %%
from osii.domain.governance import get_governance, write_governance
from osii.domain.read.catalog import load_files_catalog, load_folders_catalog
from osii.domain.scopes.collections import (
    add_documents_to_collection,
    create_collection,
    list_collection_documents,
    list_collections,
)
from osii.domain.scopes.descriptors import describe_scope
from osii.domain.scopes.membership import list_scope_file_ids

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the earlier numbered examples first.")
documents = load_files_catalog(paths.osii_root)
folders = load_folders_catalog(paths.osii_root)

heading("Root and folder scopes")
root_scope = {"scope_type": "root"}
print(describe_scope(paths.osii_root, root_scope))
print("Root members:", len(list_scope_file_ids(paths.osii_root, root_scope)))
for folder in folders:
    scope = {"scope_type": "folder", "folder_id": folder["folder_id"]}
    print("-", describe_scope(paths.osii_root, scope), "members=", len(list_scope_file_ids(paths.osii_root, scope)))

# %% [markdown]
# ## Create an idempotent collection
#
# Re-running this cell reuses the named collection and does not duplicate
# membership.

# %%
collection_name = "Purcell analysis"
collection = next(
    (item for item in list_collections(paths.osii_root) if item["name"] == collection_name),
    None,
)
if collection is None:
    collection = create_collection(
        paths.osii_root,
        name=collection_name,
        description="The bundled Purcell article and its derived knowledge products.",
        color="#2563eb",
    )

document_ids = [item["file_id"] for item in documents]
membership = add_documents_to_collection(paths.osii_root, collection["id"], document_ids)

heading("Collection scope")
print(collection)
print("Membership update:", membership)
print("Current members:", list_collection_documents(paths.osii_root, collection["id"]))
print(
    "Canonical definition:",
    paths.osii_root / "collections" / collection["id"] / "collection.toml",
)

# %% [markdown]
# ## Add portable labels and tags

# %%
sample_file_id = document_ids[0]
governance = write_governance(
    paths.osii_root,
    sample_file_id,
    sensitivity_labels=["PUBLIC DEMO"],
    tags=["fluid dynamics", "low Reynolds number", "reviewed example"],
    handling_notes="Bundled public scientific article; no access restriction.",
)

heading("Object governance sidecar")
print(governance)
print("Read back:", get_governance(paths.osii_root, sample_file_id))
print("Path:", paths.osii_root / "objects" / sample_file_id / "governance.toml")
