# %% [markdown]
# # 01 — Turn documents into grounded objects
#
# Extraction answers a narrow question: **what usable content can be recovered
# from this source, and where did it come from?** It should not decide what the
# document means to a particular research project. That later interpretation
# belongs in synthesis or enrichment.
#
# Keeping this boundary narrow lets OSII replace OCR, compare extraction
# versions, and reuse the same grounded text in many future workflows.

# %% [markdown]
# ## The extraction contract
#
# ```text
# source path + extractor choice + expert context
#                       |
#                       v
#              extraction result
#                       |
#                       v
#     OSII core commits text + manifest + provenance
# ```
#
# `expert_context` may tell an extractor what details must not be lost. It does
# not authorize the extractor to invent a summary or scientific conclusion.

# %%
import os

from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.extraction.dispatcher import dispatch_extract

from _demo_support import demo_paths, heading, processor_descriptor, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run 00_Start_here first.")

source_files = paths.source_files()
print(f"Ready to extract {len(source_files)} document(s):")
for source_file in source_files:
    print("-", source_file.relative_to(paths.source_root))

# %% [markdown]
# ## Start OCR only for sources that need it
#
# The bundled PDF is scanned, so its useful text is in pixels. The normal OSII
# stack includes a separate, full-page Tesseract service. It has different
# system dependencies from the store and can be replaced independently.
#
# From the repository root, start the normal stack:
#
# ```bash
# make dev
# ```
#
# On Windows PowerShell:
#
# ```powershell
# .\scripts\osii.ps1 dev
# ```
#
# Wait for <http://127.0.0.1:8080/health> to return `{"status":"ok"}`.
#
# Keeping OCR outside the notebook is intentional. A production extractor may
# run on a workstation, an isolated server, or specialized hardware while the
# same Python workflow and canonical store remain unchanged.

# %%
OCR_URL = "http://127.0.0.1:8080"
OCR_PROCESSOR = "local.tesseract-page-ocr"
pdf_files = [path for path in source_files if path.suffix.lower() == ".pdf"]
ocr_descriptor = processor_descriptor(OCR_URL) if pdf_files else None
ocr_ready = not pdf_files or (
    ocr_descriptor is not None and ocr_descriptor.get("name") == OCR_PROCESSOR
)

print("PDFs requiring OCR:", len(pdf_files))
print("OCR processor:", (ocr_descriptor or {}).get("name", "offline"))

if pdf_files and ocr_descriptor and ocr_descriptor.get("name") != OCR_PROCESSOR:
    print(f"Expected {OCR_PROCESSOR}; check the service running on {OCR_URL}.")

if ocr_ready and ocr_descriptor:
    # The notebook process is separate from the application containers. Add
    # the discovered endpoint explicitly so the dispatcher can select it.
    os.environ["OSII_ROOT"] = str(paths.osii_root)
    processor_urls = [
        url for url in os.environ.get("OSII_PROCESSORS", "").split(",") if url
    ]
    if OCR_URL not in processor_urls:
        processor_urls.append(OCR_URL)
    os.environ["OSII_PROCESSORS"] = ",".join(processor_urls)

# %% [markdown]
# ## Plan before executing
#
# Routing is data, not hidden control flow. Here the rule is deliberately easy
# to read: scanned PDFs use Tesseract; formats with native text use the local
# text extractor. A real deployment can replace this rule with configured
# routes while keeping the downstream object model unchanged.

# %%
def extractor_for(source_file):
    if source_file.suffix.lower() == ".pdf":
        return OCR_PROCESSOR, {"language": "eng"}
    return "native_text", {"chunk_chars": 4000}


extraction_plan = [
    (source_file, *extractor_for(source_file)) for source_file in source_files
]

for source_file, extractor_name, _ in extraction_plan:
    print(f"- {source_file.name} -> {extractor_name}")

# %% [markdown]
# ## Give the extractor domain-preservation guidance
#
# Replace this text for your field. Good guidance identifies information that
# is easy for a generic parser to damage or omit. It does not ask for analysis.

# %%
EXPERT_CONTEXT = (
    "Preserve physical quantities, equations, named entities, figure and table "
    "references, uncertainty, and important caveats."
)

print(EXPERT_CONTEXT)

# %% [markdown]
# ## Extract one file
#
# This small function is the copyable core operation. The dispatcher selects a
# local or remote implementation, then OSII owns the commit into the sidecar.

# %%
def extract_one(source_file, extractor_name, extractor_config):
    return dispatch_extract(
        extractor_name=extractor_name,
        source_path=source_file,
        data_volume_root=paths.source_root,
        osii_store=paths.osii_root,
        expert_context=EXPERT_CONTEXT,
        extractor_config=extractor_config,
    )

# %% [markdown]
# ## Apply the same operation to the corpus
#
# Sequential processing keeps the learning example transparent. The contract
# is also suitable for queues and workers because each file is independent and
# returns an explicit result.

# %%
results = []

if not ocr_ready:
    print("Extraction paused: start the Tesseract service, then rerun from discovery.")
else:
    for source_file, extractor_name, extractor_config in extraction_plan:
        result = extract_one(source_file, extractor_name, extractor_config)
        results.append(result)
        print(f"- {source_file.name} -> {result['file_id']}")

# %% [markdown]
# ## Rebuild the browsing view
#
# Folder membership and SQLite catalog rows are projections over canonical
# objects. They make browsing fast, but they can be rebuilt from the sidecar.

# %%
if results:
    root_folder_id = get_or_create_folder_id(paths.osii_root, "")
    folder_counts = build_folder_artifacts(
        resolved_files=source_files,
        data_volume_root=paths.source_root,
        shared_root=paths.source_root,
        osii_store=paths.osii_root,
        root_folder_id=root_folder_id,
    )
    rebuild_catalog(paths.osii_root)
    print("Folder rebuild summary:", folder_counts[:2])
else:
    print("Nothing new to catalog in this run.")

# %%
heading("Browsable OSII objects")
for document in load_files_catalog(paths.osii_root):
    print(f"- {document['source_relpath']}")
    print(f"  object ID: {document['file_id']}")

# %% [markdown]
# ## What to inspect before continuing
#
# Open one directory under `.osii/objects/<file-id>/`:
#
# - `text.txt` is usable extracted text;
# - `provenance.toml` names the process that produced it;
# - `manifest.jsonl` connects segments and OCR geometry to the source.
#
# Search, synthesis, and agents can now work from grounded OSII objects instead
# of repeatedly reparsing source files or trusting an opaque model context.
