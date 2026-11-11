# OSII processor modules

Independently deployable processors receive selected inputs through the
[Processor API](../docs/reference/processor-api/index.md) and return typed results.
Core owns persistence. **Toolbox** refers to frontend tools; this folder holds
backend processor modules.

| Module | Purpose |
| --- | --- |
| [banyan](banyan/README.md) | Nemotron PDF/image extraction with element provenance |
| [tika-adapter](tika-adapter/README.md) | General document extraction, with managed Apache Tika and Java |
| [osii-tesseract](osii-tesseract/README.md) | Tesseract/OpenCV region OCR |
| [llm-wiki-enrichers](llm-wiki-enrichers/README.md) | Readable and concept/entity wikis |
| [tabular-dataset-processors](tabular-dataset-processors/README.md) | CSV extraction and collection tables |

`make dev` and `.\scripts\osii.ps1 dev` prepare independent environments and
start enabled modules. Set `OSII_ENABLE_TIKA=false`, `OSII_ENABLE_BANYAN=false`,
or another module's `OSII_ENABLE_…` switch in `.env` to omit its dependency setup,
service registration, and startup. Shared dependencies remain when another
enabled processor uses the same project. See `.env.example` for every switch.
`OSII_START_PROCESSOR_MODULES=false` leaves enabled modules available for manual
startup in Setup. The former `OSII_START_TOOLBOX` spelling is a compatibility
fallback; use the new name for new configurations.

## Contributor pattern

Keep one directory per module, containing its `pyproject.toml`, implementation,
README, configuration template if needed, and focused tests. Implement the shared
`osii.processor_sdk` interface; declare accepted file types and model needs in the
Processor API descriptor. Never browse the corpus or write canonical sidecars.
Do not add module dependencies to Core or the root environment.

Banyan's code and host configuration now live together in `banyan/`. Its original
upstream subtree history remains in Git. Copy that directory's `.env.example`
to `.env` to configure Nemotron; existing private configuration moves with it.
See [extending OSII](../docs/extending/index.md) for registration and frontend
integration. Starting a module does not invoke a model or process documents.
