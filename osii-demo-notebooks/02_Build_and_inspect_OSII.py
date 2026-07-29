# This file is generated from the similarly named .ipynb notebook.
# Edit this Python companion for normal code changes; preserve the notebook as an artifact.

# %% [markdown]
# # Build and Inspect an OSII Store
#
# This notebook builds an OSII store from a source data root and performs an initial inspection of the resulting backend structure.
#
# The notebook demonstrates:
#
# - defining the source data root
# - choosing an OSII output location
# - running the ingest/build workflow
# - inspecting root, folder, and object structures
#
# The main build step uses the backend as an installed Python package through a real module invocation.

# %% [markdown]
# from pathlib import Path
# import json
# import shutil
# import subprocess
# import sys
# import textwrap

# %% [markdown]
# ## Define paths
#
# Adjust these paths if needed for your local environment.
#
# The source data root is the directory whose contents will be ingested.
# The OSII root is where the backend will write the resulting structured store.

# %%
REPO_ROOT = Path(r"C:\Users\hbkomko\OneDrive - Sandia National Laboratories\Documents\AI_tools\ai-ready-everything\ai-ready-ingest").resolve()
DATA_ROOT = REPO_ROOT / "data_volume" / "my_data"
OSII_ROOT = REPO_ROOT / "data_volume" / ".osii"

REPO_ROOT, DATA_ROOT, OSII_ROOT

# %%
assert REPO_ROOT.exists(), f"Repo root not found: {REPO_ROOT}"
assert DATA_ROOT.exists(), f"Data root not found: {DATA_ROOT}"

print("Repo root:", REPO_ROOT)
print("Data root:", DATA_ROOT)
print("OSII root:", OSII_ROOT)

# %% [markdown]
# ## Optional cleanup
#
# If an older demo OSII store exists and you want a fresh run, set `RESET_OSII` to `True`.
#
# This deletes the current `.osii` directory before rebuilding it.

# %%
RESET_OSII = False

if RESET_OSII and OSII_ROOT.exists():
    shutil.rmtree(OSII_ROOT)

print("OSII root exists before build:", OSII_ROOT.exists())

# %% [markdown]
# ## Run the build
#
# This example uses the backend's main collection-build workflow.
#
# The first run can be done without expensive folder-level synthesis if you want a quicker structural demonstration.
#
# This notebook uses the installed package through a real module invocation:
#
# - `python -m osii.build_collection`

# %%
build_cmd = [
    sys.executable,
    "-m",
    "osii.build_collection",
    "--data-root",
    str(DATA_ROOT),
    "--osii-root",
    str(OSII_ROOT),
]

print("Command:")
print(" ".join(f'"{part}"' if " " in part else part for part in build_cmd))

# %%
build_result = subprocess.run(
    build_cmd,
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
)

print("Return code:", build_result.returncode)
print()
print("STDOUT")
print("-" * 80)
print(build_result.stdout)
print()
print("STDERR")
print("-" * 80)
print(build_result.stderr)

# %% [markdown]
# ## Confirm that the OSII store now exists

# %%
assert OSII_ROOT.exists(), "OSII root was not created."
print("OSII root exists:", OSII_ROOT.exists())

# %% [markdown]
# ## Inspect the top-level OSII layout
#
# The OSII root is the current file-based implementation of the backend store.
#
# The exact contents depend on what build steps ran, but the root typically includes:
#
# - root descriptor
# - folder artifacts
# - object bundles
# - run metadata
# - embeddings area
# - collections area

# %%
top_level = sorted(p.name for p in OSII_ROOT.iterdir())
top_level

# %% [markdown]
# ## Import read helpers
#
# The backend exposes read-side helpers for inspecting the resulting store directly from Python.

# %%
from osii.domain.read.catalog import load_files_catalog, load_folders_catalog
from osii.domain.read.root import get_root_descriptor, get_root_overview_toml, get_root_synth_text
from osii.domain.read.docs import get_doc_overview, get_doc_meta
from osii.domain.read.manifest import list_manifest_records

# %% [markdown]
# ## Root descriptor
#
# The root descriptor gives the top-level identity and data-root context for the OSII store.

# %%
root_descriptor = get_root_descriptor(OSII_ROOT)
root_descriptor

# %% [markdown]
# ## Folder catalog
#
# Folder scopes are structural scopes derived from the source hierarchy.
#
# This catalog is a flat list; tree construction can be done client-side from the `path` field.

# %%
folders_catalog = load_folders_catalog(OSII_ROOT)
len(folders_catalog), folders_catalog[:10]

# %% [markdown]
# ## File catalog
#
# Objects are the stable content units in the store.
#
# The file catalog maps source-relative paths to stable object identifiers.

# %%
files_catalog = load_files_catalog(OSII_ROOT)
len(files_catalog), files_catalog[:10]

# %% [markdown]
# ## Pick one sample object
#
# The next cells inspect one object bundle in more detail.

# %%
assert files_catalog, "No files found in catalog."

sample_entry = files_catalog[0]
sample_file_id = sample_entry["file_id"]
sample_source_relpath = sample_entry["source_relpath"]

sample_file_id, sample_source_relpath

# %% [markdown]
# ## Object metadata
#
# The object metadata describes the source file identity and stable content hash.

# %% [markdown]
# ## Object overview
#
# The overview summarizes what extraction produced for the object.

# %%
sample_overview = get_doc_overview(OSII_ROOT, sample_file_id)
sample_overview

# %% [markdown]
# ## Canonical manifest records
#
# The manifest remains the canonical extraction provenance record for the object.
#
# It defines:
#
# - extracted text records
# - extracted artifacts
# - source-origin grounding

# %%
sample_manifest = list_manifest_records(OSII_ROOT, sample_file_id)
sample_manifest[:5]

# %% [markdown]
# ## Optional root synthesis inspection
#
# If root-level or folder-level synthesis has been run, synthesized artifacts may also be present.
#
# This cell checks for currently available root-level synthesis outputs.

# %%
root_overview = get_root_overview_toml(OSII_ROOT)
root_synth = get_root_synth_text(OSII_ROOT)

print("Root overview exists:", root_overview is not None)
print("Root synth exists:", root_synth is not None)

# %% [markdown]
# ## Summary
#
# This notebook built an OSII store and confirmed that the backend now contains:
#
# - a root descriptor
# - a folder catalog
# - a file catalog
# - canonical object metadata
# - canonical manifest records
#
# The next notebook will inspect objects, collections, and other backend features directly through Python in more detail.

# %%


# %%


# %%


# %%


# %%


