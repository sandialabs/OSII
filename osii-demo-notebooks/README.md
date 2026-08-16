# OSII Python walkthrough

This folder is the shortest code-first path through OSII. The examples are
ordinary Python files with Jupytext `# %%` cell markers, so you can run them in
a terminal, step through them in an IDE, or convert them to notebooks.

The walkthrough is intentionally small and sequential. It shows the actual
OSII architecture without requiring you to begin with containers or a model:

| File | What it demonstrates | Extra service required |
|---|---|---|
| `00_Setup_a_demo_workspace.py` | Show the documents that OSII will use | None |
| `01_Create_an_OSII_store.py` | File-based sidecar and rebuildable catalog | None |
| `02_Extract_documents_locally.py` | Page OCR, expert context, provenance, bounding boxes | OSII-Tesseract |
| `03_Create_local_text_previews.py` | Processor-based cited synthesis | Local synthesizer |
| `04_Browse_objects_and_create_a_collection.py` | Scopes, collections, labels, tags | None |
| `05_Build_and_search_a_lexical_index.py` | Overlapping chunks and BM25 search | None |
| `06_Build_local_embeddings.py` | Explicit lexical hashing-vector index | Local embedder |
| `07_Create_a_standard_enrichment.py` | Keyword table and entity-list artifacts | None |
| `08_Connect_an_optional_model_or_processor.py` | Ollama opt-in and package export | Ollama only for opt-in cells |

## Set up once

Use Python 3.11, which is the OSII development baseline. Create and activate a
notebook-specific virtual environment, then install everything from this
directory:

```bash
cd osii-demo-notebooks
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m ipykernel install --user --name osii-demo --display-name "OSII demo"
jupyter lab
```

On Windows PowerShell:

```powershell
cd osii-demo-notebooks
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m ipykernel install --user --name osii-demo --display-name "OSII demo"
jupyter lab
```

In Jupyter, choose the **OSII demo** kernel for the examples. The kernel
registration command only needs to be repeated if you recreate the virtual
environment.

The requirements install the local OSII core and Processor SDK, JupyterLab,
the IPython kernel, and Jupytext. No model weights are downloaded. Optional
processor services remain separate and are only needed by examples that call
them over HTTP.

## Add your documents

Put documents directly in `osii-demo-notebooks/documents/`, beside the bundled
`purcell.pdf`. That directory is the source library; OSII never modifies the
originals. Additional files placed there are ignored by Git.

Notebook 00 contains one relative path and simply displays the file count and
names:

```python
DOCUMENTS_DIR = Path("documents")
```

PDFs use OSII-Tesseract in script 02, while supported text and office formats
use the native extractor. Later scripts include plainly named example queries
and titles that you can edit for your own subject matter.

## Run as plain Python

Run the files in numerical order:

```bash
python 00_Setup_a_demo_workspace.py
python 01_Create_an_OSII_store.py
python 02_Extract_documents_locally.py
```

Continue through `08_...py`. OSII reads originals from `documents/`; `.osii`
artifacts, indexes, and exports stay under the ignored `demo-workspace/`
directory.

The Purcell PDF is scanned, so script 02 deliberately uses OSII-Tesseract and
its page-level bounding boxes. Start the required OCR service from the
repository root; the Tesseract executable must already be on `PATH`:

```bash
make dev-ocr-host
```

```powershell
.\scripts\osii.ps1 dev-ocr-host
```

Scripts 03 and 06 use the optional local synthesizer and embedder services:

```bash
make dev-synthesizer
make dev-embedder
```

Windows PowerShell equivalents:

```powershell
.\scripts\osii.ps1 dev-synthesizer
.\scripts\osii.ps1 dev-embedder
```

`make dev` or `.\scripts\osii.ps1 dev` starts the complete editable stack.

## Convert all examples

The `.py` files are the reviewable source of truth in Git. The convenience
wrapper converts every marked demo script in this folder and does not require
filenames:

```bash
python manage_notebooks.py to-notebooks
```

After editing notebooks, convert every notebook back to percent-format Python:

```bash
python manage_notebooks.py to-python
```

For direct CLI use, Jupytext supports the same operations:

```bash
jupytext --to notebook example.py
jupytext --to py:percent example.ipynb
jupytext --update --to notebook example.py
jupytext --to md --test example.ipynb
```

Run these commands with the virtual environment activated. Review the Git diff
after conversion; the Python files remain the normal review and editing format.

## What is canonical?

- Your original source files remain outside `.osii` and are never edited.
- Portable `.osii` TOML, JSONL, text, and artifact files are authoritative.
- `.osii/state/catalog.sqlite3` is a disposable acceleration layer.
- BM25 and FAISS indexes are derived and rebuildable.
- Model and Processor API services return typed results; OSII core commits the
  canonical sidecar.

For prose documentation, use the focused
[Python demonstrations guide](../docs/tutorials/python-demonstrations.md). For
extension development, start with
[Choose an extension](../docs/extending/index.md).
