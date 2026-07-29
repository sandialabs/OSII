# %% [markdown]
# # 03 — Create local text previews
#
# FirstN is the dashboard's model-free preview option. It cleans extracted text
# and keeps the first portion as an inspectable local summary; it is not an LLM
# summary.

# %%
from osii.domain.storage.ids import compute_file_id
from osii.domain.storage.folders import get_or_create_folder_id
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.synthesis.file.firstn import FirstNSynthesizer

from _demo_support import demo_paths, require_file

# %%
_, SOURCE_ROOT, OSII_ROOT = demo_paths()
source_file = SOURCE_ROOT / "experiment_notes.txt"
require_file(source_file, "Run 00_Setup_a_demo_workspace.py first.")
file_id = compute_file_id(source_file)

preview = FirstNSynthesizer().synthesize(
    osii_store=OSII_ROOT,
    file_id=file_id,
    Synthesizer_config={"max_chars": 600},
)
print(preview)
print((OSII_ROOT / "objects" / file_id / "synth.txt").read_text(encoding="utf-8"))

# Build folder manifests after extraction. They provide the catalog used by
# browsing, collections, lexical search, embeddings, and scope enrichments.
root_folder_id = get_or_create_folder_id(OSII_ROOT, "")
folder_counts = build_folder_artifacts(
    resolved_files=[source_file],
    data_volume_root=SOURCE_ROOT,
    shared_root=SOURCE_ROOT,
    osii_store=OSII_ROOT,
    root_folder_id=root_folder_id,
)
print("Folder artifacts:", folder_counts[:2])
