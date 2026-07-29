# %% [markdown]
# # 01 — Create the OSII store
#
# OSII keeps derived, inspectable data in `.osii` and never edits the source
# folder. This initializes the layout and records the corpus root descriptor.

# %%
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.store import ensure_osii_store_layout

from _demo_support import demo_paths

# %%
_, SOURCE_ROOT, OSII_ROOT = demo_paths()
layout = ensure_osii_store_layout(OSII_ROOT)
root_folder_id = get_or_create_folder_id(OSII_ROOT, "")
descriptor = write_root_toml(
    OSII_ROOT,
    root_folder_id=root_folder_id,
    host_path=str(SOURCE_ROOT),
    container_path="/data/source",
    notes="OSII Python demonstration corpus",
    tool_versions={"demo": "1"},
)

print("Store directories:", {name: str(path) for name, path in layout.items()})
print("Root descriptor:", descriptor)
