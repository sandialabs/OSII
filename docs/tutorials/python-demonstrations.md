# Python demonstrations

Use [`osii-demo-notebooks/`](https://github.com/heidikmkv/osii/tree/main/osii-demo-notebooks) for the
canonical code-first OSII walkthrough. Its numbered, Jupytext-compatible Python
files are designed to be read by a person and run in order.

## What you will build

The examples use the bundled nine-page scan of E. M. Purcell's *Life at low
Reynolds number* and then show, through the installed `osii` Python module, how
to:

1. initialize the canonical file-based `.osii` sidecar;
2. rebuild and verify the disposable SQLite read catalog;
3. OCR the scanned PDF with expert context, page provenance, and bounding boxes;
4. call a synthesizer through Processor API and let core commit its result;
5. browse root/folder/collection scopes and add portable labels and tags;
6. build overlapping retrieval chunks and a BM25 index;
7. optionally add the explicit local hashing-vector baseline;
8. create standard table and entity-list enrichments;
9. optionally use a named Ollama model and export a collection package.

The OCR, cited-preview, and hashing examples need their corresponding local
services. Each gives an exact launch command when its service is offline. No
container or model is required; OCR does require Tesseract on `PATH`.

## Install and run

Use Python 3.11–3.13. From the repository root:

```bash
cd osii-demo-notebooks
python -m pip install -r requirements.txt
python 00_Setup_a_demo_workspace.py
python 01_Create_an_OSII_store.py
python 02_Extract_documents_locally.py
```

Continue in numerical order. On Windows, substitute `py` for `python` if that
is your configured launcher.

Working data stays under `osii-demo-notebooks/demo-workspace/` and is ignored
by Git. Script `00` copies the bundled PDF there and resets only that fixed
demonstration directory.

To use personal documents, place them in the Git-ignored
`osii-demo-notebooks/user-documents/` directory and change the `SOURCE_PATH`
line in script 00 to point to `paths.notebook_dir / "user-documents"`. It also
accepts a path to one file. Originals are copied into the disposable workspace
and never modified.

## Use notebooks without making notebook JSON the source of truth

Create all canonical notebook companions:

```bash
python manage_notebooks.py to-notebooks
```

If a destination notebook already exists, this uses Jupytext's `--update`
behavior to refresh inputs while preserving outputs and notebook metadata.

After editing notebooks in Jupyter, convert them back to reviewable
Jupytext-percent Python:

```bash
python manage_notebooks.py to-python
```

The wrapper always converts all matching files. Use Jupytext directly for a
single file or a round-trip test. See the
[demonstration README](https://github.com/heidikmkv/osii/tree/main/osii-demo-notebooks) for precise commands
and the canonical file list.

## Where to go next

- To use the dashboard, return to the repository [Getting started](https://github.com/heidikmkv/osii#getting-started).
- To write a domain processor, [choose a processor kind](../extending/index.md).
- To understand the sidecar and catalog boundary, read the [store structure](../reference/osii-store.md).
- To inspect the wire contract, use the [Processor API v1 reference](../reference/processor-api/index.md).
