# OSII Python walkthrough

This folder is the shortest code-first path through OSII. The examples are
ordinary Python files with Jupytext `# %%` cell markers, so you can run them in
a terminal, step through them in an IDE, or convert them to notebooks.

The walkthrough is intentionally small and sequential. Run the numbered
examples in order. They move from choosing source documents and creating the
portable sidecar through extraction, synthesis, collections, search,
embeddings, standard enrichments, optional models, and package export. Each
example explains what it is doing before it changes or derives anything.

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

Put documents directly in `osii-demo-notebooks/demo-workspace/documents/`,
beside the bundled `purcell.pdf`. The source directory and `.osii` sidecar are
then visible next to each other. OSII never modifies the originals. Additional
files placed there are ignored by Git.

The first example contains one relative path and displays the file count and
names before initializing the OSII sidecar:

```python
DOCUMENTS_DIR = Path("demo-workspace/documents")
```

PDFs use OSII-Tesseract during extraction, while supported text and office formats
use the native extractor. Later scripts include plainly named example queries
and titles that you can edit for your own subject matter.

## Run the walkthrough

Open the generated notebooks in Jupyter and run them in numerical order. You
can also run each matching `.py` file from a terminal. OSII reads originals
from `demo-workspace/documents/`; `.osii` artifacts, indexes, and exports stay
beside them under `demo-workspace/`.

There are two alternative notebooks numbered 01. Run **one**:

- **Tesseract** is the public local OCR path and preserves page bounding boxes.
- **Shirty Textract** is the simple corporate path through the separately
  deployed `osii-shirty-bridge`.

Both write the same canonical OSII structures, so the remaining numbered
examples are identical regardless of which extractor you choose.

The Purcell PDF is scanned, so the extraction example uses OSII-Tesseract and
its page-level bounding boxes. Start the required OCR service from the
repository root in a **second terminal**, keep that terminal running, and then
return to Jupyter. The Tesseract executable must already be on `PATH`:

```bash
tesseract --version
```

On macOS, install it once with `brew install tesseract` if that command is
missing. On corporate Windows, use the approved Tesseract installation and
confirm that `tesseract.exe` is on `PATH`.

```bash
make dev-ocr-host
```

```powershell
.\scripts\osii.ps1 dev-ocr-host
```

Confirm that <http://127.0.0.1:8080/health> returns `{"status":"ok"}` before
running the extraction cells. The notebook checks this connection and skips
extraction with a readable instruction if the service is unavailable.

For real Shirty, start the sibling bridge in a second corporate terminal:

```powershell
cd ..\osii-shirty-bridge
uv run python -m app --mode real
```

The bridge holds the private Shirty dependency and credential; the public OSII
notebook does not import either. To emulate the same workflow outside the air
gap, start OSII-Tesseract and Ollama as described in the bridge README, then run:

```bash
cd ../osii-shirty-bridge
uv run python -m app --mode emulated
```

The emulator uses the same URLs but records `emulated` descriptors and
provenance. It tests the workflow without claiming local OCR is real Shirty.

The synthesis and embedding examples use optional local services:

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
