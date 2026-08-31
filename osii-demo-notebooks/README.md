# Learn OSII through Python

This series is the code-first introduction to OSII. It is for a researcher,
engineer, or subject-matter expert who wants to understand the architecture by
building a small, inspectable library one step at a time.

The examples are ordinary Python files with Jupytext `# %%` cells. You can run
them as scripts, step through them in an IDE, or open their generated notebook
counterparts in JupyterLab. The `.py` files are the reviewable source of truth.

## The idea behind OSII

OSII starts from a simple observation: source files often live much longer than
the application, model, or analysis pipeline currently being used on them.
Useful intelligence about those files therefore should not be trapped inside a
single UI, vector database, model provider, or agent framework.

OSII builds a portable, inspectable sidecar beside the originals:

```text
your documents                  OSII sidecar
---------------                 ------------
report.pdf       ----------->   .osii/objects/.../text.txt
notes.docx                       .osii/objects/.../provenance.toml
experiment.csv                  .osii/collections/...
                                 .osii/enrichments/...
```

That boundary leads to four design choices:

1. **Grounding before generation.** Extracted text, source locations, and
   provenance remain available for inspection and citation.
2. **Canonical data before indexes.** BM25, FAISS, SQLite, and model outputs are
   useful, but they are derived and rebuildable. Ordinary `.osii` files remain
   authoritative.
3. **Replaceable computation.** Extractors, synthesizers, embedders, and
   enrichers are independent processors. OSII core validates their responses
   and owns persistence.
4. **One vocabulary for people and agents.** Objects, scopes, provenance, and
   standard artifacts can be used by the dashboard, Python, REST, MCP, or a
   future agent workflow without inventing a new storage model each time.

The result is a set of composable building blocks. A research team can replace
OCR without replacing search, add a domain table enricher without forking the
core, or let an agent combine existing scopes and artifacts without handing it
unrestricted access to a user's filesystem.

## Two Python packages, two responsibilities

The monorepo installs two packages used in this series:

- `osii` contains the core store, extraction commit logic, scopes, artifacts,
  indexing, and search. The current research API is explicit: some examples
  import focused modules such as `osii.domain.scopes.collections` rather than a
  single top-level convenience object.
- `osii_processor_sdk` is the stable public extension surface. It provides
  typed requests and responses plus one-method interfaces for extractors,
  synthesizers, embedders, and enrichers.

The first part of the series teaches the core concepts. The final three
examples teach the friendly SDK surface you should copy when adding your own
domain logic.

## Set up the notebook environment once

Use Python 3.11, the OSII host-development baseline. Run these commands from
this directory because `requirements.txt` contains paths relative to the
monorepo:

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

Choose the **OSII demo** kernel in Jupyter.

There are intentionally two environments in a full development checkout:

| Environment | Owner | Purpose |
|---|---|---|
| `osii-demo-notebooks/.venv` | You/Jupyter | Interactive examples and the notebook kernel |
| `osii-env` | `make dev` or `scripts/osii.ps1 dev` | Automatically managed environment for the running OSII application services |

Do not choose `osii-env` as the notebook kernel. You normally do not activate
or edit it; the development launcher creates and updates it. Optional processor
services also remain separate processes reached over HTTP.

## The learning path

Run the core walkthrough in order. For step 01, choose one extraction path.

| Step | Question answered |
|---|---|
| `00_Start_here` | What is an OSII store, and which parts are canonical? |
| `01_Extract_documents_with_Tesseract` | How does local extraction become grounded OSII data? |
| `02_Create_local_text_previews` | Why is synthesis separate from extraction? |
| `03_Browse_and_create_a_collection` | How do objects and scopes become agent-ready context? |
| `04_Build_and_search_a_lexical_index` | How does zero-model retrieval remain grounded? |
| `05_Build_local_embeddings` | How can vector retrieval be added without becoming canonical? |
| `06_Create_standard_enrichments` | How do domain products stay portable and UI-independent? |
| `07_Connect_an_optional_model_or_processor` | Where do optional models and transfer fit? |

Then use the extension track as copyable starting points:

| Step | Extension built |
|---|---|
| `08_Write_a_custom_extractor` | Source bytes to grounded text segments |
| `09_Write_a_custom_synthesizer` | Existing text to cited Markdown |
| `10_Write_a_custom_enricher` | Existing text to a standard entity-list artifact |

Each extension example runs the processor directly in Python before wrapping it
as an HTTP app. This keeps domain logic easy to test: the network boundary is
an adapter, not the place where the research algorithm has to live.

## Add your own documents

Put files in `demo-workspace/documents/`, beside the bundled `purcell.pdf`.
Additional files there are ignored by Git. OSII reads the originals in place
and writes all derived data under `demo-workspace/.osii/`.

The bundled PDF is scanned. To run the public OCR path, install Tesseract and
start the OCR service from the repository root in a second terminal:

```bash
tesseract --version
make dev-ocr-host
```

Windows PowerShell:

```powershell
tesseract --version
.\scripts\osii.ps1 dev-ocr-host
```

Wait until <http://127.0.0.1:8080/health> returns `{"status":"ok"}`. The
notebook checks the service and skips extraction with a readable message if it
is unavailable.

For an OpenAI-compatible model endpoint, set the endpoint and credential, then
start the bundled HTTP adapter from the repository root in a second terminal.
It provides model-backed synthesis, embeddings, and chat; extraction remains a
local or Processor API capability:

```powershell
$env:OPENAI_BASE_URL = "https://models.example.test/v1"
$env:OPENAI_API_KEY = "your-api-key-here"
.\scripts\osii.ps1 dev-model-bridge
```

Outside the corporate environment, use the deterministic OpenAI-compatible emulator and
point the same adapter at `http://127.0.0.1:8096/api/v1`. Exact macOS and
PowerShell commands are in
[`services/model-provider-bridge/README.md`](../services/model-provider-bridge/README.md).

Later examples can use the independent baseline services:

```bash
make dev-synthesizer
make dev-embedder
```

Windows PowerShell:

```powershell
.\scripts\osii.ps1 dev-synthesizer
.\scripts\osii.ps1 dev-embedder
```

`make dev` or `.\scripts\osii.ps1 dev` starts the complete editable stack.

## Convert the reviewable sources

With the notebook environment active:

```bash
python manage_notebooks.py to-notebooks
```

To bring human notebook edits back into percent-format Python:

```bash
python manage_notebooks.py to-python
```

Always review the resulting diff. Notebook JSON is a generated/human-facing
artifact; the paired Python files are the normal place for code review.

## What remains canonical

- Original source files remain outside `.osii` and are never edited.
- Portable `.osii` TOML, JSONL, text, and standard artifacts are authoritative.
- `.osii/state/catalog.sqlite3`, BM25, and FAISS indexes are rebuildable.
- Processor services return typed results; OSII core commits the sidecar.
- A model may propose a useful artifact, but provenance determines what can be
  defended later by a person or an agent.

For deeper design material, continue with
[Architecture](../docs/concepts/architecture.md),
[Choose an extension](../docs/extending/index.md), and
[Processor API v1](../docs/reference/processor-api/index.md).
