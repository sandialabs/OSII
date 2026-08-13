# Python demonstrations

Use [`osii-demo-notebooks/`](https://github.com/heidikmkv/osii/tree/main/osii-demo-notebooks) for the
canonical code-first OSII walkthrough. Its numbered, Jupytext-compatible Python
files are designed to be read by a person and run in order.

## What you will build

The examples generate a small four-document corpus and then show, through the
installed `osii` Python module, how to:

1. initialize the canonical file-based `.osii` sidecar;
2. rebuild and verify the disposable SQLite read catalog;
3. extract documents locally with expert context and provenance;
4. call a synthesizer through Processor API and let core commit its result;
5. browse root/folder/collection scopes and add portable labels and tags;
6. build overlapping retrieval chunks and a BM25 index;
7. optionally add the explicit local hashing-vector baseline;
8. create standard table and entity-list enrichments;
9. optionally use a named Ollama model and export a collection package.

Only the cited-preview and hashing examples need their corresponding lightweight
service. They skip with an exact launch command when the service is offline.
Every other example runs without a container or model.

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

Generated data stays under `osii-demo-notebooks/demo-workspace/` and is ignored
by Git. Script `00` resets only that fixed demonstration directory.

## Use notebooks without making notebook JSON the source of truth

Create all canonical notebook companions:

```bash
python manage_notebooks.py to-notebooks
```

If a destination notebook already exists, this uses Jupytext's `--update`
behavior to refresh inputs while preserving outputs and notebook metadata.
Pass `--force` only when you intentionally want a clean notebook with outputs
removed.

After editing notebooks in Jupyter, convert them back to reviewable
Jupytext-percent Python:

```bash
python manage_notebooks.py to-python --force
```

Both commands accept individual filenames. Existing targets are protected
when converting back to Python unless `--force` is present. Run
`python manage_notebooks.py test-roundtrip` for Jupytext's non-writing
round-trip test. See the
[demonstration README](https://github.com/heidikmkv/osii/tree/main/osii-demo-notebooks) for precise commands
and the canonical file list.

## Where to go next

- To use the dashboard, return to the repository [Getting started](https://github.com/heidikmkv/osii#getting-started).
- To write a domain processor, [choose a processor kind](../extending/index.md).
- To understand the sidecar and catalog boundary, read the [store structure](../reference/osii-store.md).
- To inspect the wire contract, use the [Processor API v1 reference](../reference/processor-api/index.md).
