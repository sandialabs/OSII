# Local and intermittently connected operation

OSII has a useful guaranteed baseline with no container runtime, network call,
credential, or model cache.

| Capability | Guaranteed baseline | Optional enhancement |
|---|---|---|
| Extraction | native text-layer PDF, Office, RTF, and text/data formats | Tika, OCR, Shirty Textract, domain processor |
| Synthesis | cited extractive Markdown preview | selected Ollama, OpenAI-compatible, or Shirty chat model |
| Embedding | 384D token/bigram hashing (lexical) | selected semantic embedding model |
| Search | BM25; hashing similarity | provider/model-specific semantic FAISS index |
| Enrichment | statistics and keywords table | domain Processor API service |
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
provider request until a provider and exact model are enabled. Run applications
without any processor or bridge using `make dev-core`.

Use `make dev-ollama` after installing and starting Ollama separately. OSII
queries `/api/tags` to show installed models but never pulls one. When Tools
reports a missing model, run the displayed command yourself, for example:

```bash
ollama pull nomic-embed-text
```

Then enter that exact name in **Tools → Model providers** and enable the
provider. The Windows command is `.\scripts\osii.ps1 dev-ollama`.

On Windows, append `-DryRun` to any host profile command to validate its
service plan without opening ports, for example
`.\scripts\osii.ps1 dev-corporate -DryRun`.

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
