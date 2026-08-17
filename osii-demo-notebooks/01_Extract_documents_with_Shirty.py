# %% [markdown]
# # 01 alternative — Extract through the Shirty bridge
#
# In the corporate environment, the bridge calls real Shirty Textract. Outside
# the corporate environment, its explicit emulator mode calls OSII-Tesseract.
# Both modes exercise the same bridge URL and OSII commit workflow, but the
# emulator is clearly labeled in provenance. OSII core still owns the `.osii`
# files and never changes the originals.

# %%
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.processors.remote import RemoteExtractor

from _demo_support import demo_paths, get_json, heading, processor_descriptor, require_path


paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run the start-here example first.")
source_files = paths.source_files()

print(f"Ready to extract {len(source_files)} document(s) with Shirty Textract.")
for source_file in source_files:
    print("-", source_file.relative_to(paths.source_root))

# %% [markdown]
# ## Connect to the Shirty bridge
#
# Start the separately checked-out `osii-shirty-bridge` in a second terminal
# and keep it running. In the corporate environment:
#
# ```powershell
# cd ..\osii-shirty-bridge
# uv run python -m app --mode real
# ```
#
# Outside the corporate environment, first start Tesseract and Ollama as
# described in the bridge README, then use `--mode emulated`. The bridge
# process—not this notebook—holds provider dependencies and credentials. If
# your team deploys a shared bridge, change the single URL below.

# %%
SHIRTY_BRIDGE_URL = "http://127.0.0.1:8096"
SHIRTY_EXTRACTOR_URL = f"{SHIRTY_BRIDGE_URL}/extractor"

health = get_json(f"{SHIRTY_EXTRACTOR_URL}/health")
descriptor = processor_descriptor(SHIRTY_EXTRACTOR_URL)
bridge_ready = (
    health is not None
    and health.get("status") == "ok"
    and health.get("dependency") != "credentials-missing"
    and descriptor is not None
)

if bridge_ready:
    print(f"Shirty bridge is ready in {health.get('mode')} mode:", descriptor["display_name"])
else:
    print("Shirty Textract is not ready yet.")
    print("Start the bridge in a second terminal, then rerun this cell.")
    if health:
        print("Bridge status:", health)

# %% [markdown]
# ## Extract one document at a time
#
# The bridge receives source bytes and returns grounded text segments. OSII
# validates that response and commits text, manifests, and provenance locally.
# `EXPERT_CONTEXT` is plain-language guidance you can replace for your domain.

# %%
EXPERT_CONTEXT = (
    "Preserve physical quantities, equations, named entities, figure and table "
    "references, uncertainty, and important caveats."
)

results = []
if not bridge_ready:
    print("Extraction skipped: connect the Shirty bridge and rerun from the connection check.")
else:
    extractor = RemoteExtractor(descriptor)
    heading("Extract one file at a time")
    for source_file in source_files:
        result = extractor.extract(
            source_path=source_file,
            data_volume_root=paths.source_root,
            osii_store=paths.osii_root,
            expert_context=EXPERT_CONTEXT,
            extractor_config={},
        )
        results.append(result)
        print(f"- {source_file.name} via {descriptor['name']} -> {result['file_id']}")

# %% [markdown]
# ## Make completed documents browsable
#
# This is the same OSII commit and catalog step used by the local alternative.
# Downstream notebooks do not need to know which extractor produced the text.

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
# ## Outside the corporate environment
#
# Run the sibling bridge with `uv run python -m app --mode emulated`. That mode
# delegates OCR to OSII-Tesseract while preserving the bridge's real HTTP
# contract. Its descriptor and committed metadata say `emulated`, so it cannot
# be confused with corporate Shirty output. This is a workflow emulator, not a
# claim that local OCR has the same extraction quality as Shirty Textract.
