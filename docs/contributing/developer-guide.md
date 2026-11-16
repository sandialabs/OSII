# Contributor guide

## Start here

Read:

1. the [architecture](../concepts/architecture.md);
2. the [OSII store structure](../reference/osii-store.md);
3. the [single-file walkthrough](../tutorials/single-file.md);
4. the [Processor API](../reference/processor-api/index.md) when changing an
   extension boundary.

The main repository boundaries are:

- `osii-core/osii`: core domain logic, persistence, REST API, worker, and grounded RAG under `osii/rag`;
- `osii-core/osii/processor_sdk`: public processor contracts and service helpers, included in `osii`;
- `osii-core/processor-sdk`: copyable processor examples and contract tests;
- `osii-core/services`: guaranteed local, independently addressable processor hosts;
- `osii-dashboard/dashboard`: React and TypeScript user interface;
- `osii-mcp`: agent-facing OSII tools;
- `osii-processor-modules`: optional processors with independent dependencies and images.

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
`osii-core/osii/extraction/`. Preserve canonical text and manifest
semantics, and keep synthesis and embeddings downstream.

### Core synthesis

Read the [synthesis architecture](../concepts/synthesis.md), then inspect
`osii-core/osii/synthesis/`. Synthesizers consume extracted OSII data and
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

OSII supports Python 3.11 through 3.13. The checked-in `.python-version`, host
startup script and examples use Python 3.12 so local and deployed
behavior do not drift. Python 3.14 is not yet supported by the pinned
FastAPI/Pydantic dependency set.

```bash
make test
```

To check that OSII can be installed without the monorepo, build its source
distribution and wheel and install into a temporary, clean environment:

```bash
uv run --no-project --python 3.12 --with build python scripts/check_python_distribution.py
```

Run this explicitly when checking standalone package installation. Both
`osii.processor_sdk` and the compatibility imports `osii_processor_sdk` ship in
one distribution. Processor services depend on `osii` and install Core's normal
dependencies; package installation does not launch any services.

For documentation:

```bash
python -m pip install -r docs/requirements.txt
python scripts/check_docs_links.py
mkdocs build --strict
```

Do not commit runtime stores, source documents, generated sites, caches,
credentials, or model weights.

## CI and extension checks

Use the full branch CI commands in `.github/workflows/ci.yml`; do not exclude
known failures to claim a passing suite. The first local Core job intentionally
runs without PostgreSQL drivers. PostgreSQL fixtures must check their explicit
test database URL before importing optional dependencies. CI then exercises real
PostgreSQL contracts in an isolated database. Never point those tests at an app
or corpus database.

`python scripts/check_extensions.py` prevents obsolete backend directory names,
missing manifests, and missing offline test declarations. `--test` runs each
module's declared contract tests independently. Toolbox is frontend UI;
processor modules are backend implementations. Historical `toolbox.*` Processor
API IDs remain compatible and are not directory references.
