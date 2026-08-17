# %% [markdown]
# # 02 — OCR the Purcell PDF with page provenance
#
# The bundled Purcell article is a scanned PDF with no usable text layer, so
# PDFs use OSII-Tesseract for page OCR and bounding boxes. Other supported text
# and office files use the dependency-free native extractor.
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

from _demo_support import demo_paths, get_json, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run scripts 00 and 01 first.")
source_files = paths.source_files()

OCR_URL = "http://127.0.0.1:8080"
pdf_files = [path for path in source_files if path.suffix.lower() == ".pdf"]
if pdf_files and get_json(f"{OCR_URL}/health") is None:
    raise RuntimeError(
        "OSII-Tesseract is not running. From the repository root, run "
        "`make dev-ocr-host` (macOS/Linux) or "
        "`.\\scripts\\osii.ps1 dev-ocr-host` (Windows), then rerun this file. "
        "The Tesseract executable must be available on PATH."
    )

EXPERT_CONTEXT = (
    "Preserve physical quantities, equations, named entities, figure and table "
    "references, uncertainty, and important caveats."
)

heading("Extract one file at a time")
results = []
for source_file in source_files:
    extractor_name = "osii_tesseract" if source_file.suffix.lower() == ".pdf" else "native_text"
    extractor_config = (
        {"osii_tesseract_base_url": OCR_URL, "language": "en"}
        if extractor_name == "osii_tesseract"
        else {"chunk_chars": 4000}
    )
    result = dispatch_extract(
        extractor_name=extractor_name,
        source_path=source_file,
        data_volume_root=paths.source_root,
        osii_store=paths.osii_root,
        expert_context=EXPERT_CONTEXT,
        extractor_config=extractor_config,
    )
    results.append(result)
    print(f"- {source_file.name} via {extractor_name} -> {result['file_id']}")

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
# The object is now visible under `.osii/objects/<file-id>/`. Open `meta.toml`,
# `provenance.toml`, `manifest.jsonl`, and `text.txt` to see the portable record.
# Manifest regions retain normalized OCR geometry for source highlighting. The
# next script asks a separate synthesizer service to create a cited preview.
