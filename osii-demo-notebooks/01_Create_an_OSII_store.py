# %% [markdown]
# # 01 — Initialize the portable OSII store
#
# Canonical OSII data is file based. Text, manifests, provenance, collections,
# and enrichments remain readable without running OSII. SQLite is a derived
# catalog that makes browsing fast and can always be rebuilt from those files.

# %%
from osii.domain.catalog_db import rebuild_catalog, verify_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.store import ensure_osii_store_layout

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()
require_path(paths.source_root, "Run 00_Setup_a_demo_workspace.py first.")

layout = ensure_osii_store_layout(paths.osii_root)
root_folder_id = get_or_create_folder_id(paths.osii_root, "")
root_descriptor = write_root_toml(
    paths.osii_root,
    root_folder_id=root_folder_id,
    host_path=str(paths.source_root),
    container_path="/data/source",
    notes="Bundled Purcell PDF Python demonstration",
    tool_versions={"demo_walkthrough": "1"},
)

# Building an empty catalog is harmless. Later examples rebuild it after each
# authoritative file change, just as the application does.
catalog_status = rebuild_catalog(paths.osii_root)

heading("Canonical store layout")
for name, path in layout.items():
    print(f"{name:12} {path.relative_to(paths.workspace)}")

print("\nRoot descriptor:", root_descriptor.relative_to(paths.workspace))
print("Catalog build:", catalog_status)
print("Catalog verification:", verify_catalog(paths.osii_root))

# %% [markdown]
# Look inside `demo-workspace/.osii/root.toml`: it is normal TOML. The derived
# catalog lives at `.osii/state/catalog.sqlite3`; deleting that one database
# does not delete the canonical OSII knowledge layer.
