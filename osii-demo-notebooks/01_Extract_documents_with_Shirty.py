# %% [markdown]
# # 01 alternative — Put a private extractor behind a public boundary
#
# Some valuable processors cannot live in the public repository. They may use
# licensed software, controlled credentials, sensitive models, or specialized
# hardware. OSII handles this by standardizing the **contract**, not the
# implementation.
#
# This example reaches Shirty Textract through a small bridge. Real corporate
# Shirty and the public emulator expose the same Processor API shape. OSII core
# still validates and commits the result; the bridge never writes `.osii`.

# %% [markdown]
# ## Why this is modularity rather than indirection
#
# A clean service boundary lets different teams own different concerns:
#
# - a domain team owns extraction quality and provider credentials;
# - OSII core owns object identity, provenance validation, and persistence;
# - search, synthesis, the dashboard, and agents consume the resulting object
#   without importing the private dependency.
#
# The same downstream notebooks work after either step-01 alternative.

# %%
from osii.domain.catalog_db import rebuild_catalog
from osii.domain.processing.folder_rebuild import build_folder_artifacts
from osii.domain.read.catalog import load_files_catalog
from osii.domain.storage.folders import get_or_create_folder_id
from osii.processors.remote import RemoteExtractor

from _demo_support import demo_paths, get_json, processor_descriptor, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run 00_Start_here first.")

source_files = paths.source_files()
for source_file in source_files:
    print("-", source_file.relative_to(paths.source_root))

# %% [markdown]
# ## Discover before calling
#
# A processor descriptor is a machine-readable promise: identity, version,
# kind, capabilities, and configurable values. Discovery allows OSII—or a
# future planning agent—to decide whether a processor fits a job before sending
# document bytes.
#
# Start the sibling bridge in a second corporate terminal:
#
# ```powershell
# cd ..\osii-shirty-bridge
# uv run python -m app --mode real
# ```
#
# Outside the corporate environment, use its documented `--mode emulated`
# path. Emulation tests orchestration while preserving an honest provenance
# label; it does not claim equivalent extraction quality.

# %%
SHIRTY_BRIDGE_URL = "http://127.0.0.1:8096"
SHIRTY_EXTRACTOR_URL = f"{SHIRTY_BRIDGE_URL}/extractor"

health = get_json(f"{SHIRTY_EXTRACTOR_URL}/health")
descriptor = processor_descriptor(SHIRTY_EXTRACTOR_URL)

print("Health:", health or "offline")
print("Descriptor:", descriptor or "unavailable")

# %%
bridge_ready = (
    health is not None
    and health.get("status") == "ok"
    and health.get("dependency") != "credentials-missing"
    and descriptor is not None
)

if bridge_ready:
    print(f"Ready: {descriptor['display_name']} ({health.get('mode')} mode)")
else:
    print("Start or configure the Shirty bridge, then rerun the discovery cells.")

# %% [markdown]
# ## Create the client adapter
#
# `RemoteExtractor` translates between a source file and the typed Processor
# API request/response. The private implementation stays behind HTTP; the rest
# of the Python workflow uses an ordinary object.

# %%
extractor = RemoteExtractor(descriptor) if bridge_ready else None

EXPERT_CONTEXT = (
    "Preserve physical quantities, equations, named entities, figure and table "
    "references, uncertainty, and important caveats."
)

# %% [markdown]
# ## Extract one file through the bridge

# %%
def extract_one(source_file):
    return extractor.extract(
        source_path=source_file,
        data_volume_root=paths.source_root,
        osii_store=paths.osii_root,
        expert_context=EXPERT_CONTEXT,
        extractor_config={},
    )

# %% [markdown]
# ## Apply the same contract to the corpus

# %%
results = []

if extractor is None:
    print("Extraction paused until the bridge is ready.")
else:
    for source_file in source_files:
        result = extract_one(source_file)
        results.append(result)
        print(f"- {source_file.name} -> {result['file_id']}")

# %% [markdown]
# ## Rebuild the shared browsing projection
#
# This is deliberately identical to the local extraction path. Once the core
# has committed a valid extraction, consumers use OSII object semantics rather
# than branching on the vendor that produced them.

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
print("Browsable OSII objects:")
for document in load_files_catalog(paths.osii_root):
    print(f"- {document['source_relpath']} -> {document['file_id']}")

# %% [markdown]
# The important result is not that OSII knows about Shirty. It is that OSII does
# **not need** to know Shirty's private Python API. A typed, inspectable boundary
# lets the extractor evolve independently while preserving a stable corpus for
# retrieval, research comparison, and future agent workflows.
