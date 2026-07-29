# Contributor guide

## Start here

Read:

1. the [architecture](../concepts/architecture.md);
2. the [OSII store structure](../reference/osii-store.md);
3. the [single-file walkthrough](../tutorials/single-file.md);
4. the [Processor API](../reference/processor-api/index.md) when changing an
   extension boundary.

The main repository boundaries are:

- `ai-ready-ingest/osii`: core domain logic, persistence, REST API, and worker;
- `packages/osii-processor-sdk`: public processor contracts and service helpers;
- `services`: independently deployable processor implementations;
- `osii-dashboard/dashboard`: React and TypeScript user interface;
- `ai-ready-rag-chat`: grounded chat orchestration;
- `ai-ready-mcp`: agent-facing OSII tools.

## Design invariants

- The OSII core owns canonical persistence.
- External processors are replaceable compute services and never receive a
  writable `.osii` mount.
- Extraction, synthesis, embedding, and enrichment remain separate stages.
- Dashboard, REST, chat, and MCP interfaces consume the same logical scopes and
  artifacts.
- Derived results retain defensible provenance to source text or structure.
- Public processor compatibility is versioned through Processor API v1.

## Common contribution paths

### Core extraction

Read the [extraction architecture](../concepts/extraction.md), then inspect
`ai-ready-ingest/osii/extraction/`. Preserve canonical text and manifest
semantics, and keep synthesis and embeddings downstream.

### Core synthesis

Read the [synthesis architecture](../concepts/synthesis.md), then inspect
`ai-ready-ingest/osii/synthesis/`. Synthesizers consume extracted OSII data and
must not reparse source files.

### External processors

Follow [Extend OSII](../extending/index.md). Prefer a small external service
over adding new subject-specific dependencies to the core.

### Dashboard

Frontend code lives under `osii-dashboard/dashboard/src`. Keep API access in
typed client modules, server state in TanStack Query, and user interaction
state in the relevant React component. Standard artifacts should use the
shared renderer rather than processor-specific pages.

## Validate changes

From the repository root:

OSII development uses Python 3.11 through 3.13. `uv` reads the included
`.python-version` file and selects Python 3.13 automatically; Python 3.14 is
not yet supported by the pinned FastAPI/Pydantic dependency set.

```bash
make test
```

For documentation:

```bash
python -m pip install -r docs/requirements.txt
python scripts/check_docs_links.py
mkdocs build --strict
```

Do not commit runtime stores, source documents, generated sites, caches,
credentials, or model weights.
