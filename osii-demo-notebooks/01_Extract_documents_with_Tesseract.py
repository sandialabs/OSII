# %% [markdown]
# # 01 — Extract documents with provenance
#
# Extraction turns each source document into grounded text that later steps can
# search, summarize, embed, and enrich. OSII records which extractor was used
# and where each text segment came from. It never changes the source document.

# %%
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.extraction.dispatcher import dispatch_extract

from _demo_support import demo_paths, get_json, heading, require_path


paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run the start-here example first.")
source_files = paths.source_files()

print(f"Ready to extract {len(source_files)} document(s).")
for source_file in source_files:
    print("-", source_file.relative_to(paths.source_root))

# %% [markdown]
# ## Start OCR before processing a scanned PDF
#
# The bundled Purcell PDF contains page images rather than selectable text.
# OSII therefore sends it to the separate OSII-Tesseract OCR service. The
# service runs locally on your computer and returns page text plus bounding
# boxes; OSII core then writes that result into `.osii`.
#
# First, check the required OCR program in a terminal:
#
# ```bash
# tesseract --version
# ```
#
# On a Mac, install it once with `brew install tesseract` if that command is
# missing. On a corporate Windows computer, use the approved Tesseract package
# and confirm that `tesseract.exe` is on `PATH`.
#
# Open a **second terminal**, leave this notebook open, and run the following
# command from the repository root:
#
# **macOS or Linux**
#
# ```bash
# make dev-ocr-host
# ```
#
# **Windows PowerShell**
#
# ```powershell
# .\scripts\osii.ps1 dev-ocr-host
# ```
#
# Keep that terminal running. Tesseract itself must be available on `PATH`.
# When the service is ready, <http://127.0.0.1:8080/health> returns
# `{"status":"ok"}`. Then rerun the connection-check cell below.

# %%
OCR_URL = "http://127.0.0.1:8080"
pdf_files = [path for path in source_files if path.suffix.lower() == ".pdf"]
ocr_ready = not pdf_files or get_json(f"{OCR_URL}/health") is not None

if ocr_ready:
    print("OCR service is ready.")
else:
    print("OCR service is not running yet. Start it in a second terminal using the instructions above.")
    print("After its health page responds, rerun this cell and continue.")

# %% [markdown]
# ## Extract one document at a time
#
# PDFs use OSII-Tesseract because the demonstration PDF is scanned. Supported
# text and Office files use the built-in native-text extractor. `EXPERT_CONTEXT`
# gives an extractor useful domain guidance without changing the source.

# %%
EXPERT_CONTEXT = (
    "Preserve physical quantities, equations, named entities, figure and table "
    "references, uncertainty, and important caveats."
)

results = []
if not ocr_ready:
    print("Extraction skipped: start OSII-Tesseract and rerun from the connection check.")
else:
    heading("Extract one file at a time")
    for source_file in source_files:
        extractor_name = (
            "osii_tesseract" if source_file.suffix.lower() == ".pdf" else "native_text"
        )
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

# %% [markdown]
# ## Make completed documents browsable
#
# OSII now writes folder membership and rebuilds its disposable SQLite catalog.
# The canonical text and provenance remain ordinary files under `.osii`.

# %%
if not results:
    print("Catalog update skipped because no documents were extracted in this run.")
else:
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
# Each extracted object now has a directory under `.osii/objects/<file-id>/`.
# Its `text.txt` holds extracted text, `provenance.toml` records how extraction
# happened, and `manifest.jsonl` connects text segments and OCR boxes back to
# source pages. The next example creates a cited preview from that grounded text.
