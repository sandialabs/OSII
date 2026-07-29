# %% [markdown]
# # 04 — Browse objects and create a collection
#
# Collections are lightweight user groupings over canonical OSII object IDs.
# They do not duplicate the original documents or extracted data.

# %%
from osii.domain.scopes.collections import add_documents_to_collection, create_collection, list_collections
from osii.domain.storage.ids import compute_file_id

from _demo_support import demo_paths, require_file

# %%
_, SOURCE_ROOT, OSII_ROOT = demo_paths()
source_file = SOURCE_ROOT / "experiment_notes.txt"
require_file(source_file, "Run 00_Setup_a_demo_workspace.py first.")
file_id = compute_file_id(source_file)

collection = next((item for item in list_collections(OSII_ROOT) if item["name"] == "Calibration experiments"), None)
if collection is None:
    collection = create_collection(
        OSII_ROOT,
        name="Calibration experiments",
        description="Files about calibration drift and repeat measurements.",
    )
membership = add_documents_to_collection(OSII_ROOT, collection["id"], [file_id])

print("Collection:", collection)
print("Membership update:", membership)
print("All collections:", list_collections(OSII_ROOT))
