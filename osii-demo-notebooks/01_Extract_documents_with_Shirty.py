# %% [markdown]
# # 01 alternative — Extract with Shirty through OSII's HTTP adapter
#
# Some valuable processors cannot live in the public repository. They may use
# licensed software, controlled credentials, sensitive models, or specialized
# hardware. OSII handles this by standardizing the **contract**, not the
# implementation.
#
# This example reaches Shirty Textract through OSII's bundled model-provider
# service. The adapter uses Shirty's documented HTTP endpoint directly; it does
# not install the private Shirty Python package. OSII core still validates and
# commits the result, and the adapter never writes `.osii`.

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
# In the corporate environment, set the Shirty credentials and start OSII's
# bundled adapter from the repository root in a second terminal:
#
# ```powershell
# $env:SHIRTY_BASE_URL = "https://shirty.sandia.gov/api/v1"
# $env:SHIRTY_API_KEY = "your-api-key-here"
# .\scripts\osii.ps1 dev-model-bridge
# ```
#
# Outside the corporate environment, run the test emulator on port 8096, point
# these same environment variables at it, and start `dev-model-bridge`. The
# repository README gives the exact commands. Emulation validates the contract;
# it does not claim equivalent extraction quality.

# %%
MODEL_BRIDGE_URL = "http://127.0.0.1:8095"
SHIRTY_EXTRACTOR_URL = f"{MODEL_BRIDGE_URL}/shirty/extractor"

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
    print(f"Ready: {descriptor['display_name']}")
else:
    print("Start or configure OSII's model-provider bridge, then rerun these cells.")

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
# ## Extract one file through the adapter

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
