# %% [markdown]
# # 11 — Treat datasets as grounded OSII sources
#
# Documents are only one kind of evidence. A CSV row can be grounded to its
# source line just as a PDF passage can be grounded to a page and bounding box.
# This example calls a copyable custom extractor, inspects its standard table,
# and explains when several source files should become a collection product.

# %% [markdown]
# ## Start the dataset demonstration
#
# From the OSII Core repository root, import the public example corpus:
#
# ```bash
# make demo-data
# ```
#
# Then start the optional tabular processors. This notebook directly calls the
# extractor on port 8097; start both services when you also want the dashboard
# collection-table workflow.
#
# ```bash
# make toolbox-run TOOL=tabular
# ```
# On Windows PowerShell, import the files with:
#
# ```powershell
# .\scripts\osii.ps1 demo-data
# .\scripts\osii.ps1 toolbox-run -Tool tabular
# ```
#
# Wait for <http://127.0.0.1:8097/health> to return `{"status":"ok"}`.
# For dashboard use, register both processor URLs in **Setup** or add them to
# `OSII_PROCESSORS` before starting OSII.
#
# The Iris and Wine data are bundled with scikit-learn. The import step creates
# temporary ZIP archives and unpacks ordinary CSV partitions beneath
# `osii-data/source/example-datasets/`; it does not download dataset contents.

# %%
from pathlib import Path
import base64
import hashlib

from osii.processor_sdk import (
    DocumentInput,
    ExtractionRequest,
    ProcessorClient,
    ProcessorClientError,
)


def repository_root() -> Path:
    """Find the checkout from Jupyter, an IDE, or a terminal."""
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "osii-core").is_dir() and (candidate / "osii-toolbox").is_dir():
            return candidate
    raise RuntimeError("Open this notebook from inside an OSII repository checkout.")


IRIS_CSV = repository_root() / "osii-data/source/example-datasets/iris/data/setosa.csv"
EXTRACTOR_URL = "http://127.0.0.1:8097"

if not IRIS_CSV.is_file():
    raise RuntimeError("Run `make demo-data` from the repository root, then rerun this cell.")

print("Source:", IRIS_CSV.resolve())
print("Bytes:", IRIS_CSV.stat().st_size)

# %% [markdown]
# ## Ask the processor what it does
#
# A descriptor is the stable, human-readable contract that lets OSII expose a
# subject-matter expert's processor without custom frontend code.

# %%
client = ProcessorClient(EXTRACTOR_URL)
try:
    descriptor = client.descriptor()
except ProcessorClientError:
    descriptor = None
    print(
        "CSV extractor is offline. Run `make toolbox-run TOOL=tabular` "
        "or `.\\scripts\\osii.ps1 toolbox-run -Tool tabular`, then rerun this cell."
    )

if descriptor:
    print(descriptor.display_name)
    print(descriptor.description)
    print("Outputs:", descriptor.capabilities.output_kinds)

# %% [markdown]
# ## Extract one CSV source
#
# The request carries explicit bytes. The processor cannot browse the OSII
# library or write `.osii`; core remains responsible for committing validated
# output and provenance.

# %%
source_bytes = IRIS_CSV.read_bytes()
file_id = "sha256-" + hashlib.sha256(source_bytes).hexdigest()
response = None
if descriptor:
    response = client.extract(
        ExtractionRequest(
            request_id="dataset-demo-1",
            document=DocumentInput(
                file_id=file_id,
                filename=IRIS_CSV.name,
                media_type="text/csv",
                content_base64=base64.b64encode(source_bytes).decode("ascii"),
            ),
            expert_context="Iris measurements use centimeters; retain the target class.",
        )
    )

if response:
    table = response.artifacts[0].standard_data
    print(f"Grounded rows: {len(response.segments)}")
    print(f"Table columns: {[column.label for column in table.columns]}")

# %% [markdown]
# Every table row has provenance back to the CSV source line. The first five
# rows below are the same standard artifact shape rendered by the dashboard.

# %%
if response:
    for row, provenance in zip(table.rows[:5], table.row_provenance[:5], strict=True):
        print(row)
        print("  source:", provenance[0].source_origin)

# %% [markdown]
# ## See the same product in OSII
#
# In the dashboard, open **Intake**, select the Iris `data` folder, and choose
# **CSV dataset table extractor** for `.csv`. Each file becomes a grounded OSII
# object. Open an object's **Extractions** tab and expand **Extracted data
# products** to see the sortable table.
#
# A single source table belongs to extraction. A table combining the Setosa,
# Versicolor, and Virginica files is different: it is a derived result over an
# explicit scope. Create an **Iris dataset** collection containing those three
# objects, open **Derived artifacts**, expand **More available enrichment
# methods**, and run **Dataset collection table**. The generic table viewer
# renders it without knowing anything about Iris or this processor.

# %% [markdown]
# ## What to inspect
#
# - Original CSV partitions remain under `osii-data/source`.
# - Grounded text rows and extraction artifacts live under each object's
#   canonical `.osii/objects/...` sidecar.
# - The merged table belongs to the collection's `enrichments` directory.
# - The SQLite catalog accelerates discovery but can still be rebuilt.
#
# The same pattern works for experimental run folders: write the narrow parser
# once, return typed rows and provenance, and let OSII provide scopes, storage,
# dashboard rendering, APIs, and future agent access.
