# %% [markdown]
# # 02 — Extract documents with the guaranteed local baseline
#
# `native_text` runs in Python and handles common text/data
# files, text-layer PDFs, DOCX, PPTX, XLSX, and RTF. Scanned PDFs still need an
# optional OCR processor.
#
# Extraction is foundational: it creates stable object IDs, canonical text,
# provenance, and manifests. Synthesis, embeddings, search, and enrichment read
# those products instead of reopening the original files.

# %%
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.extraction.dispatcher import dispatch_extract

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run scripts 00 and 01 first.")
source_files = paths.source_files()

EXPERT_CONTEXT = (
    "This is a generated sensor-test corpus. Experiment numbers identify runs; "
    "measurement drift is reported as a percentage."
)

heading("Extract one file at a time")
results = []
for source_file in source_files:
    result = dispatch_extract(
        extractor_name="native_text",
        source_path=source_file,
        data_volume_root=paths.source_root,
        osii_store=paths.osii_root,
        expert_context=EXPERT_CONTEXT,
        extractor_config={"chunk_chars": 4000},
    )
    results.append(result)
    print(f"- {source_file.name} -> {result['file_id']}")

# Folder manifests are canonical files describing structural scope membership.
root_folder_id = get_or_create_folder_id(paths.osii_root, "")
folder_counts = build_folder_artifacts(
    resolved_files=source_files,
    data_volume_root=paths.source_root,
    shared_root=paths.source_root,
    osii_store=paths.osii_root,
    root_folder_id=root_folder_id,
)
rebuild_catalog(paths.osii_root)

heading("Browsable document catalog")
for document in load_files_catalog(paths.osii_root):
    print(f"- {document['source_relpath']}\n  {document['file_id']}")

print("\nFolder rebuild summary:", folder_counts[:2])

# %% [markdown]
# Each object is now visible independently under `.osii/objects/<file-id>/`.
# Open `meta.toml`, `provenance.toml`, `manifest.jsonl`, and `text.txt` to see
# the portable record. The next script asks a separate synthesizer service to
# create cited previews and lets OSII core commit them.
