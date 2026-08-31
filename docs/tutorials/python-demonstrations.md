# Learn OSII through Python

The canonical code-first walkthrough lives in `osii-demo-notebooks/`. Its
numbered Jupytext-compatible Python files are designed to be read by a person,
run in order, and converted into notebooks when desired.

## What the series teaches

The walkthrough is organized around OSII's design choices rather than around
the dashboard:

1. keep source documents untouched and create a portable `.osii` sidecar;
2. distinguish canonical files from rebuildable catalogs and indexes;
3. extract grounded text while preserving provenance;
4. keep extraction, synthesis, embeddings, and enrichment replaceable;
5. use explicit object, folder, collection, and root scopes;
6. retrieve evidence locally before adding optional models;
7. return standard artifacts that work for both people and agents;
8. export a collection sidecar without bundling original sources.

The final extension track uses the public `osii_processor_sdk` package to build
and test a small extractor, synthesizer, and enricher. Those examples are
intended to be copied into independent domain-processor services.

## Set up the notebook kernel

Use Python 3.11. Run the installation from the demonstration directory because
its requirements contain monorepo-relative package paths.

macOS or Linux:

```bash
cd osii-demo-notebooks
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m ipykernel install --user --name osii-demo --display-name "OSII demo"
python manage_notebooks.py to-notebooks
jupyter lab
```

Windows PowerShell:

```powershell
cd osii-demo-notebooks
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m ipykernel install --user --name osii-demo --display-name "OSII demo"
python manage_notebooks.py to-notebooks
jupyter lab
```

Choose the **OSII demo** kernel and run the examples in numerical order. The
step-01 extraction path uses local Tesseract. Configure an OpenAI-compatible
model endpoint later for model-backed synthesis, embeddings, or chat.

The notebook environment and host application environment have different
jobs:

| Environment | Purpose |
|---|---|
| `osii-demo-notebooks/.venv` | Jupyter kernel and interactive Python examples |
| `osii-env` | Automatically managed application-service environment used by `make dev` and `scripts/osii.ps1 dev` |

Do not select `osii-env` as the notebook kernel. Optional extractor,
synthesizer, embedder, and model services run separately and are reached over
their typed HTTP contracts.

## Bring your own documents

Put personal files in `osii-demo-notebooks/demo-workspace/documents/`, beside
the bundled Purcell PDF. Additional files there are ignored by Git. OSII reads
the originals in place and writes derived content under
`osii-demo-notebooks/demo-workspace/.osii/`.

The bundled PDF is scanned, so the Tesseract path requires the local OCR
service. Each service-dependent example explains the exact command and checks
the endpoint before doing work.

## Keep Python reviewable

The percent-format `.py` files are the source of truth. Generate all notebook
companions with:

```bash
python manage_notebooks.py to-notebooks
```

After intentionally editing notebooks in Jupyter, convert them back with:

```bash
python manage_notebooks.py to-python
```

Always review the diff after conversion. Notebook JSON remains a human-facing
artifact rather than the normal code-review format.

## Continue learning

- [Architecture](../concepts/architecture.md)
- [Choose a processor kind](../extending/index.md)
- [Develop a processor](../extending/processor-development.md)
- [Processor API v1](../reference/processor-api/index.md)
- [OSII store structure](../reference/osii-store.md)
