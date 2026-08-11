# Local and intermittently connected operation

OSII has a useful guaranteed baseline with no container runtime, network call,
credential, or model cache.

| Capability | Guaranteed baseline | Optional enhancement |
|---|---|---|
| Extraction | native text-layer PDF, Office, RTF, and text/data formats | Tika, OCR, Shirty Textract, domain processor |
| Synthesis | cited extractive Markdown preview | selected Ollama, OpenAI-compatible, or Shirty chat model |
| Embedding | 384D token/bigram hashing (lexical) | selected semantic embedding model |
| Search | BM25; hashing similarity | provider/model-specific semantic FAISS index |
| Enrichment | statistics and keywords table | LLM wiki through the selected model-backed synthesizer; domain Processor API service |
| Chat | grounded extractive answer | selected model provider |
| Browse/API/MCP | local dashboard, backend, and MCP | same contracts |

## Host-native profiles

The normal development path is entirely bare metal:

```bash
make dev
```

```powershell
.\scripts\osii.ps1 dev
```

It starts the API, worker, chat, MCP, dashboard, four baseline processors, and
the lightweight provider bridge from editable source. The bridge makes no
generation or embedding request until that capability is used; Tools performs
only model discovery. Run applications without any processor or bridge using
`make dev-core`.

Host Python dependencies live in the ignored `osii-env/` directory. OSII uses
that visible name because current macOS Python releases can skip editable
package path files beneath a hidden `.venv` directory.

Normal `make dev` is Ollama-first when the separately installed Ollama service
is reachable. In **Tools → Model providers**, OSII queries `/api/tags` and shows
the installed models beside the endpoint configuration. The two approved US
starter models are:

- `all-minilm`, a roughly 46 MB Microsoft-origin embedding model.
- `llama3.2:1b`, a roughly 1.3 GB Meta chat and synthesis model.

Select **Download** to ask Ollama to pull a missing starter model and show its
progress. OSII bundles no model weights. Downloads are limited to
`OSII_OLLAMA_ALLOWED_MODELS`; corporate administrators can extend that list
with other approved models.

The equivalent manual command remains available, for example:

```bash
ollama pull all-minilm
```

`make dev-ollama` and `.\scripts\osii.ps1 dev-ollama` remain explicit aliases
for this profile. Disable the Ollama provider in Tools to return chat,
synthesis, and embedding to their guaranteed local baselines. A higher-priority
enabled OpenAI-compatible or Shirty provider replaces Ollama capability by
capability, without changing the rest of OSII.

On Windows, append `-DryRun` to any host profile command to validate its
service plan without opening ports, for example
`.\scripts\osii.ps1 dev-corporate -DryRun`.

## Add and reprocess documents

The Intake page separates **Add files**, **Process library**, and **Activity**.
Use Process library after installing a model to add embeddings or summaries to
documents that were extracted earlier. Use **Upgrade extraction** when a better
extractor becomes available; OSII preserves both extraction versions and lets
you decide whether the new result becomes primary. See
[Extraction versions and downstream lineage](../reference/extraction-versions.md).

## Generate an LLM wiki

With a model-backed synthesizer selected in Tools, OSII can compose that
capability into a standard wiki-Markdown enrichment. Generate a document wiki
from the document's **Wiki** tab or a collection wiki from the collection view.
The operation runs in the background, records the actual provider and model,
and never substitutes the extractive preview while labeling the result as an
LLM wiki. See the [LLM wiki walkthrough](../tutorials/llm-wiki.md).

Two additional dependency-free examples produce a frequency-ranked table of
lemmatized noun/adjective 2-, 3-, and 4-grams and a grounded list of named
entity candidates. Both use standard Processor API artifact formats; see
[Example keyword and entity enrichments](../tutorials/example-enrichments.md).

`make dev-corporate` registers the separately deployed Shirty bridge as first
choice and Ollama as an optional fallback. The corresponding Windows command
is `.\scripts\osii.ps1 dev-corporate`. The private Shirty package is resolved
only inside the sibling `osii-shirty-bridge` repository.

## Failure behavior

- Chat and synthesis follow the configured order and visibly report the
  provider actually used. Their final fallback is extractive.
- Embedding retries and resumes its own checkpoint. It never substitutes a
  different provider or model into an existing vector index.
- Semantic search falls back to BM25 when query embedding is unavailable.
- Shirty Textract may fall back to native extraction only for formats whose
  usable text layer can be handled natively. Scanned documents remain pending
  with an OCR/Textract explanation.

Semantic indexes live under provider/model-specific directories and record
provider, model, digest when supplied, dimensions, normalization, chunking,
and creation time. Changing model or dimensions creates a different vector
space and requires a rebuild. Hashing is never labeled semantic.

## Optional containers

Use `make dev-containers` when editable applications should use containerized
Tika and Tesseract. Use `make build && make run` for packaged deployment parity.
Ollama and Shirty remain separately managed services reached through configured
URLs; OSII images do not contain them or their model files.

## Storage and disk diagnostics

Canonical text, manifests, provenance, synthesis, enrichments, and collection
membership remain inspectable `.osii` files. `.osii/state/catalog.sqlite3` is a
derived WAL-mode read catalog and may be deleted and rebuilt. Operational queue
state remains in `jobs.sqlite3`.

```bash
make catalog-verify
make catalog-rebuild
make doctor
```

The PowerShell script exposes the same command names. `doctor` reports common
ignored disk consumers—including Python environments, `node_modules`, model
caches, OSII data, and Podman storage—and never deletes them.
