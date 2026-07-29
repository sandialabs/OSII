# %% [markdown]
# # 02 — Extract a document with the local Tika service
#
# This uses the same `DocumentExtractor` capability as the dashboard. Tika is
# local and bundled with the standard Compose stack; no model gateway is used.

# %%
import os

from osii.extraction.dispatcher import dispatch_extract

from _demo_support import demo_paths, require_file

# %%
_, SOURCE_ROOT, OSII_ROOT = demo_paths()
source_file = SOURCE_ROOT / "experiment_notes.txt"
require_file(source_file, "Run 00_Setup_a_demo_workspace.py first.")

# For a direct local run, start Tika separately or change this URL.
os.environ.setdefault("TIKA_URL", "http://localhost:9998")

result = dispatch_extract(
    extractor_name="tika",
    source_path=source_file,
    data_volume_root=SOURCE_ROOT,
    osii_store=OSII_ROOT,
)
FILE_ID = result["file_id"]
print(result)

# %% [markdown]
# `FILE_ID` is stable for this file content. The extracted text, manifest, and
# provenance are now under `.osii/objects/<FILE_ID>/`.
