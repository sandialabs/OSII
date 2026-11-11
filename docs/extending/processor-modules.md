# Discoverable processor modules

A contributor adds one directory under `osii-processor-modules/`, with a
`processor-module.toml`, `pyproject.toml`, implementation, tests, and README.
There is no central Python module list to edit. Restart `make dev` (Windows:
`.\scripts\osii.ps1 dev`) to discover the module, prepare its independent
environment, register its processors, and make service controls available in
Setup. Discovery reads manifests only; it does not import implementation code.

Toolbox refers to frontend tools. A collection data card **processor** is an
enricher that receives collection text and returns a standard artifact. A
Toolbox page for generating or viewing cards is a separate
[frontend extension](frontend-tools.md). No frontend code is required just to
register a processor or configure its settings in Setup.

## A collection data card manifest

Place this file at `osii-processor-modules/collection-data-card/processor-module.toml`:

```toml
schema_version = 1
id = "collection-data-card"
extras = []

[[processors]]
id = "collection-data-card"
processor_id = "example.collection-data-card"
kind = "enricher"
display_name = "Collection data card"
description = "Creates a data card from a selected collection."
command = ["-m", "uvicorn", "data_card.main:app"]
port = 8110
model_requirements = { chat = "required" }
```

Use `osii.processor_sdk.Enricher` and `create_processor_app` to implement the
service. The Processor API descriptor must use the manifest's `processor_id`
as its `name`, and the same `kind`. Declare collection support in the descriptor's
`capabilities.scope_types`. Return standard artifacts through the API; Core
validates and persists results. See the [enricher contract](../reference/processor-api/enrichment.md).
The manifest registers and launches the service; its runtime descriptor remains
the contract for processing inputs and outputs.

The example automatically defines these deployment overrides:

```dotenv
OSII_ENABLE_COLLECTION_DATA_CARD=false
OSII_COLLECTION_DATA_CARD_PORT=18110
```

Users put these overrides in the root `.env`; no change to Core, the launcher,
or the central `.env.example` is needed. Document the generated switches in the
module's README or configuration template. An absent enable switch means enabled.
A false switch omits dependency preparation, service registration, and startup;
saved overrides and processing history remain intact. When several processors
share a project, its environment remains if another processor still needs it.

`OSII_START_PROCESSOR_MODULES=false` defers enabled processors until they are
started from Setup. It does not omit their registrations. The older
`OSII_START_TOOLBOX` spelling remains a fallback when the new switch is absent.

## Manifest version 1

Discovery reads only `*/processor-module.toml` directly below the modules folder,
in deterministic directory order. Nested files, hidden directories, environments,
and source files are not searched. A module directory cannot escape this folder
through a symlink. `OSII_PROCESSOR_MODULES_DIR` can explicitly select another
trusted module directory; relative paths resolve against the checkout.

Top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Required integer `1` |
| `id` | Required unique module ID, lowercase words separated by hyphens |
| `extras` | Optional list of Python extras to install for the whole module |
| `processors` | One or more `[[processors]]` tables; each is a separate service |

Processor fields:

| Field | Meaning |
| --- | --- |
| `id` | Required unique service ID; derives `OSII_ENABLE_<ID>` and the default port variable |
| `processor_id` | Required Processor API descriptor name, such as `example.collection-data-card` |
| `registration_id` | Optional stable key for `tools.toml`; defaults to `id` |
| `kind` | Required `extractor`, `synthesizer`, `embedder`, or `enricher` |
| `display_name`, `description` | Required text used in Setup and logs |
| `command` | Required Python argument array, e.g. `["run.py", "enricher"]`; never a shell command |
| `port` | Required default port, integer 1–65535 |
| `port_env` | Optional override name; defaults to `OSII_<ID>_PORT` |
| `aliases` | Optional legacy processor IDs |
| `requires` | Optional executables to check for Setup's prerequisite message, e.g. `["tesseract"]` |
| `model_requirements` | Optional table mapping `chat` or `embedding` to `required` or `optional` |
| `model_access` | `gateway` or `none`; inferred from model requirements if omitted |
| `capabilities` | Optional offline metadata, including accepted `file_extensions` |
| `config_schema` | Optional offline settings schema; the live descriptor supplies processing configuration when available |
| `health_path` | Adapter liveness path; defaults to `/health` |
| `readiness_path` | Operational readiness path; defaults to `health_path` |
| `readiness_config` | Saved processor-setting keys to pass as query parameters to the readiness endpoint; non-secret values only |

Hyphens become underscores and IDs are uppercased in environment variable names.
For example `collection-data-card` becomes `COLLECTION_DATA_CARD`.
`command` runs as `uv run … python <command> --host 127.0.0.1 --port <port>` in the
module directory. The entry point must accept those host and port arguments.
The launcher synchronizes each enabled project once with its declared extras;
manual starts also use those extras. Modules do not share Core's environment.

Manifests are trusted local deployment code, not a remote plugin marketplace.
Review contributed commands and dependencies before starting them. Do not store
credentials in manifests. Module-specific environment variables can be read by
the implementation; root `.env` values are forwarded to child processes, apart
from Core-only storage settings. They need no central Python registration. Use the model gateway for model-backed processors;
keep operational secrets in the deployment environment.

## Configuration and readiness

Manifest defaults supply registrations. Existing `tools.toml` overrides take
precedence while preserving module metadata, and explicit environment opt-outs
suppress the module even if it has saved settings. Normal Setup controls still
save model bindings and processor configuration. Describe processing options in
the descriptor's `config_schema`: Setup renders the fields, and Core sends saved
settings with requests. No new environment variable is needed for each option.

If a service is stopped or unavailable, Setup retains a gray entry with its
manifest-provided name and configuration schema. Available services use their
live descriptors. Setup reports a clear error if a descriptor name or kind does
not match the effective module registration. Setup's question-mark help identifies the implementation
directory, module manifest, and active overrides file.

Adapter liveness and upstream readiness can differ. Tika declares
`readiness_path = "/upstream-health"` and
`readiness_config = ["tika_endpoint"]`; saved addresses are passed to that check.
The default upstream address remains owned by the module. Other modules can
supply similar checks without changing Core.

Unknown fields, unsupported schema versions, invalid values, duplicate module,
service, registration, or processor identities, and conflicting effective ports
produce errors naming the manifest. Existing IDs, aliases, enable switches, port
variables, and model bindings are preserved for the migrated modules.

## Validate a new module

1. Run its tests in its isolated environment, using the extras declared in the manifest.
2. Inspect the service plan with
   `uv run --no-project --python 3.12 python scripts/dev_stack.py --dry-run`
   (Windows: `.\scripts\osii.ps1 dev -DryRun`). This does not install or start modules.
3. Start the normal development stack and check Setup for the processor, settings,
   prerequisites, and service controls. Starting a service does not process documents.
4. Process one selected document or collection and inspect the returned artifact
   and provenance. Core alone owns canonical commits.

The repository's discovery tests add a temporary collection data card module and
exercise discovery, startup planning, overrides, opt-outs, Setup registration,
and service controls without editing any central lists.
