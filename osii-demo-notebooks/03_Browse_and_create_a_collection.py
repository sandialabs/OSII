# %% [markdown]
# # 03 — Turn files into explicit, reusable context
#
# A future agent should not receive "everything this process can read" as its
# implicit context. OSII represents context as inspectable scopes over stable
# objects. A person, UI, API client, or agent can all name the same scope and
# see which objects it contains.
#
# This example compares structural folders with intentional collections, then
# adds portable governance metadata.

# %% [markdown]
# ## The four scope types
#
# - **object** — one stable content unit;
# - **folder** — membership inherited from source organization;
# - **collection** — a logical grouping chosen for a task or research question;
# - **root** — the complete library.
#
# The contents of a scope are explicit. Processing code should not need to know
# whether the set came from a folder tree, a saved research collection, or an
# agent's authorized work plan.

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

from _demo_support import demo_paths, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the extraction example first.")

documents = load_files_catalog(paths.osii_root)
folders = load_folders_catalog(paths.osii_root)

print(f"Objects: {len(documents)}")
print(f"Folders: {len(folders)}")

# %% [markdown]
# ## Inspect the root scope

# %%
root_scope = {"scope_type": "root"}
root_members = list_scope_file_ids(paths.osii_root, root_scope)

print(describe_scope(paths.osii_root, root_scope))
print("Members:", root_members)

# %% [markdown]
# ## Inspect structural folder scopes
#
# Folders answer "where did these files live?" They are valuable provenance,
# but physical organization is not always the right unit for analysis.

# %%
for folder in folders:
    folder_scope = {"scope_type": "folder", "folder_id": folder["folder_id"]}
    member_ids = list_scope_file_ids(paths.osii_root, folder_scope)
    print(f"- {describe_scope(paths.osii_root, folder_scope)}")
    print(f"  members: {len(member_ids)}")

# %% [markdown]
# ## Create an intentional collection
#
# Collections answer "which objects belong together for this purpose?" Moving
# a file is unnecessary: collection membership is stored in the sidecar and
# can overlap with other collections.
#
# The cell is idempotent. Rerunning it reuses the named collection, which is a
# useful property for reproducible notebooks and agent plans.

# %%
COLLECTION_NAME = "Purcell analysis"

collection = next(
    (item for item in list_collections(paths.osii_root) if item["name"] == COLLECTION_NAME),
    None,
)

if collection is None:
    collection = create_collection(
        paths.osii_root,
        name=COLLECTION_NAME,
        description="The bundled Purcell article and its derived knowledge products.",
        color="#2563eb",
    )

print(collection)

# %% [markdown]
# ## Add objects without copying originals

# %%
document_ids = [document["file_id"] for document in documents]
membership_result = add_documents_to_collection(
    paths.osii_root,
    collection["id"],
    document_ids,
)

print("Membership update:", membership_result)

# %%
collection_scope = {
    "scope_type": "collection",
    "collection_id": collection["id"],
}
collection_members = list_collection_documents(paths.osii_root, collection["id"])

print(describe_scope(paths.osii_root, collection_scope))
print("Members:", collection_members)
print(
    "Canonical definition:",
    paths.osii_root / "collections" / collection["id"] / "collection.toml",
)

# %% [markdown]
# A collection is now a reusable unit for search, synthesis, enrichment,
# export, or an agent task. The same object can participate in many scopes
# without duplicating source bytes or losing its identity.

# %% [markdown]
# ## Add portable governance awareness
#
# Labels, tags, and handling notes travel with an object's sidecar. They help a
# person or agent make responsible choices, but they are metadata—not access
# control. Authorization must still be enforced by the surrounding system.

# %%
sample_file_id = document_ids[0]

governance = write_governance(
    paths.osii_root,
    sample_file_id,
    sensitivity_labels=["PUBLIC DEMO"],
    tags=["fluid dynamics", "low Reynolds number", "reviewed example"],
    handling_notes="Bundled public scientific article; no access restriction.",
)

print(governance)

# %%
print("Read back:", get_governance(paths.osii_root, sample_file_id))
print("Stored at:", paths.osii_root / "objects" / sample_file_id / "governance.toml")

# %% [markdown]
# The architectural payoff is composability: a later workflow can select a
# collection, inspect its governance labels, retrieve grounded passages, and
# request an enrichment without learning the original folder layout or parsing
# private application state.
