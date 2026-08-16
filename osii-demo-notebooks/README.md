# OSII Python walkthrough

This folder is the shortest code-first path through OSII. The examples are
ordinary Python files with Jupytext `# %%` cell markers, so you can run them in
a terminal, step through them in an IDE, or convert them to notebooks.

The walkthrough is intentionally small and sequential. It shows the actual
OSII architecture without requiring you to begin with containers or a model:

| File | What it demonstrates | Extra service required |
|---|---|---|
| `00_Setup_a_demo_workspace.py` | Generate a safe four-file corpus | None |
| `01_Create_an_OSII_store.py` | File-based sidecar and rebuildable catalog | None |
| `02_Extract_documents_locally.py` | Extraction, expert context, provenance | None |
| `03_Create_local_text_previews.py` | Processor-based cited synthesis | Local synthesizer |
| `04_Browse_objects_and_create_a_collection.py` | Scopes, collections, labels, tags | None |
| `05_Build_and_search_a_lexical_index.py` | Overlapping chunks and BM25 search | None |
| `06_Build_local_embeddings.py` | Explicit lexical hashing-vector index | Local embedder |
| `07_Create_a_standard_enrichment.py` | Keyword table and entity-list artifacts | None |
| `08_Connect_an_optional_model_or_processor.py` | Ollama opt-in and package export | Ollama only for opt-in cells |

## Set up once

Use Python 3.11, 3.12, or 3.13. From the repository root:

```bash
cd osii-demo-notebooks
python -m pip install -r requirements.txt
```

On Windows PowerShell, the same commands work with `py` if that is your Python
launcher:

```powershell
cd osii-demo-notebooks
py -m pip install -r requirements.txt
```

The requirements install editable copies of the local OSII core and Processor
SDK, Jupytext, JupyterLab, and the IPython kernel. They do not download model
weights. Optional processor services remain separate and are only needed by
the examples that call them over HTTP.

## Run as plain Python

Run the files in numerical order:

```bash
python 00_Setup_a_demo_workspace.py
python 01_Create_an_OSII_store.py
python 02_Extract_documents_locally.py
```

Continue through `08_...py`. Generated source files, `.osii` artifacts, indexes,
and exports stay under the ignored `demo-workspace/` directory. Rerun `00` to
reset only that generated workspace.

Scripts 03 and 06 give a friendly instruction and exit successfully when their
optional local service is offline. Start the individual service from the
repository root:

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

## Convert every Python example to a notebook

The `.py` files are the reviewable source of truth in Git. This creates all
canonical notebook companions without touching the three archived legacy
notebooks or their short same-named Python redirect pages:

```bash
python manage_notebooks.py to-notebooks
```

When a notebook already exists, the wrapper uses Jupytext's canonical
`--update --to notebook` operation: input cells are refreshed while outputs
and notebook metadata are preserved. To intentionally replace the complete
notebook and discard its outputs:

```bash
python manage_notebooks.py to-notebooks --force
```

Convert one file by passing its name or stem:

```bash
python manage_notebooks.py to-notebooks 05_Build_and_search_a_lexical_index.py
```

## Convert edited notebooks back to Python

After making human edits in Jupyter, convert all canonical notebook companions
back to reviewable percent-format Python:

```bash
python manage_notebooks.py to-python --force
```

Or convert only the notebook you changed:

```bash
python manage_notebooks.py to-python 05_Build_and_search_a_lexical_index.ipynb --force
```

Review the resulting Git diff before committing. Notebook JSON is deliberately
not the normal review or agent-editing format; agents are instructed to work
from the paired `.py` files unless a human explicitly asks otherwise.

Test every existing canonical notebook for stable round-trip conversion without
writing files:

```bash
python manage_notebooks.py test-roundtrip
```

The helper is only a batch/file-selection wrapper. It delegates conversion to
the standard `python -m jupytext` CLI, so the equivalent one-file commands are:

```bash
python -m jupytext --to py:percent example.ipynb
python -m jupytext --update --to notebook example.py
```

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
