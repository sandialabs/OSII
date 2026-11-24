# OSII processor modules

Independently deployable processors receive selected inputs through the
[Processor API](../docs/reference/processor-api/index.md) and return typed results.
Core owns persistence. **Toolbox** refers to frontend tools; this folder holds
backend processor modules.

| Module | Purpose |
| --- | --- |
| [banyan](banyan/README.md) | Nemotron PDF/image extraction with element provenance |
| [osii-tesseract](osii-tesseract/README.md) | Tesseract/OpenCV region OCR |
| [llm-wiki-enrichers](llm-wiki-enrichers/README.md) | Readable and concept/entity wikis |
| [tabular-dataset-processors](tabular-dataset-processors/README.md) | CSV extraction and collection tables |
| [whisper](whisper/README.md) | Opt-in local speech-to-text extraction with timestamps |
| [vlm-endpoint](vlm-endpoint/README.md) | Opt-in image and PDF extraction through your vision model endpoint |
| [ocria](ocria/README.md) | Opt-in OCRia-nano-1 CPU OCR; separately licensed model |

## Copy the optional extractors into an existing checkout

Download the `osii-processor-modules` branch as a ZIP and extract it into a
temporary folder. Copy the `whisper/`, `vlm-endpoint/`, and `ocria/` directories
you want from its `osii-processor-modules/` folder into the same folder in your
existing OSII checkout. Copy whole module directories, not just the Python files.
Do not replace the rest of your checkout with the ZIP: it is a branch snapshot.
If the target checkout already supports `enabled_by_default` in processor
manifests, you only need the module directories. For older checkouts, also
merge this branch's small opt-in manifest change in
`osii-core/osii/processor_modules.py` at the same relative path. Do not overwrite
unrelated changes. No shared dependency-lock changes are needed.
Follow the module's README to enable it and restart the launcher.

`make dev` and `.\scripts\osii.ps1 dev` prepare independent environments and
start enabled modules. Set `OSII_ENABLE_BANYAN=false`
or another module's `OSII_ENABLE_…` switch in `.env` to omit its dependency setup,
service registration, and startup. Shared dependencies remain when another
enabled processor uses the same project. The existing switches are illustrated in `.env.example`; new switches are derived
from each manifest without editing that central file.
`OSII_START_PROCESSOR_MODULES=false` leaves enabled modules available for manual
startup in Setup. The former `OSII_START_TOOLBOX` spelling is a compatibility
fallback; use the new name for new configurations.

## Contributor pattern

Keep one directory per module, containing `processor-module.toml`, `pyproject.toml`, implementation,
README, configuration template if needed, and focused tests. Implement the shared
`osii.processor_sdk` interface; declare accepted file types and model needs in the
Processor API descriptor. Never browse the corpus or write canonical sidecars.
Do not add module dependencies to Core or the root environment.
Declare offline contract tests in `[tool.osii.ci]` in `pyproject.toml`.
`python scripts/check_extensions.py --test` validates and tests the discovered
modules on either branch without a central workflow list.
The manifest declares commands, ports, extras, and registrations. OSII discovers it
automatically; no central launcher or Core list needs editing. See the
[manifest authoring guide](../docs/extending/processor-modules.md).

Banyan's code and host configuration now live together in `banyan/`. Its original
upstream subtree history remains in Git. Copy that directory's `.env.example`
to `.env` to configure Nemotron; existing private configuration moves with it.
See [extending OSII](../docs/extending/index.md) for registration and frontend
integration. Starting a module does not invoke a model or process documents.

The former Tika adapter and managed Java runtime are preserved on
`archive/tika-2026-11-19`. They are not registered or started on `main`.
