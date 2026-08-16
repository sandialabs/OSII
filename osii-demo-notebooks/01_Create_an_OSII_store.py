# %%
from pathlib import Path

from osii.domain.catalog_db import rebuild_catalog, verify_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.store import ensure_osii_store_layout


documents_dir = Path("documents").resolve()
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
