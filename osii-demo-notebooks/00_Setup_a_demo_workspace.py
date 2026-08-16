# %% [markdown]
# # 00 — Welcome and prepare the Purcell PDF
#
# OSII turns ordinary source files into a portable, inspectable sidecar while
# leaving the originals untouched. This walkthrough uses one bundled document:
# E. M. Purcell's classic 1977 article, *Life at low Reynolds number*.
#
# Run the numbered files in order. Working data stays inside
# `demo-workspace/`, which Git ignores.

# %%
from __future__ import annotations

import shutil

from _demo_support import demo_paths, heading, require_path


paths = demo_paths()

# Edit this one line to use either one document or a directory of documents.
# `user-documents/` is ignored by Git and is a safe place for your own files.
SOURCE_PATH = paths.notebook_dir / "purcell.pdf"

source_path = SOURCE_PATH.expanduser().resolve()
require_path(source_path, "Set SOURCE_PATH to an existing file or directory.")
if source_path == paths.workspace.resolve() or paths.workspace.resolve() in source_path.parents:
    raise RuntimeError("SOURCE_PATH must be outside demo-workspace, which this script resets.")

# This is intentionally the only destructive operation in the walkthrough.
# The target is a fixed child of osii-demo-notebooks, never a user-selected
# directory. Source documents themselves are never modified.
if paths.workspace.exists():
    shutil.rmtree(paths.workspace)

paths.source_root.mkdir(parents=True)
paths.exports.mkdir(parents=True)

if source_path.is_file():
    shutil.copy2(source_path, paths.source_root / source_path.name)
else:
    for source_file in sorted(path for path in source_path.rglob("*") if path.is_file()):
        destination = paths.source_root / source_file.relative_to(source_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)

if not paths.source_files():
    raise RuntimeError(f"SOURCE_PATH contains no files: {source_path}")

# %% [markdown]
# ## One real document
#
# The nine-page scanned article combines prose, equations, diagrams, physical
# quantities, and examples of microorganisms swimming. It gives extraction,
# provenance, retrieval, and enrichment something substantial to work with.

# %%
heading("Source documents copied into the demo workspace")
for source_file in paths.source_files():
    print("-", source_file.relative_to(paths.source_root).as_posix())
print(f"\nSource files: {paths.source_root}")
print(f"OSII sidecar: {paths.osii_root}")

# %% [markdown]
# Next, `01_Create_an_OSII_store.py` initializes the portable `.osii` sidecar.
# No service, container, database server, or model is needed yet. Because the
# PDF is scanned, script 02 will use OSII-Tesseract rather than pretending it
# has a usable text layer.
