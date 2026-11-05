# OSII Toolbox

Optional processor implementations live in this repository. They receive explicit
Processor API requests and return typed results; Core owns persistence. They
start automatically with `make dev` and the equivalent PowerShell command.

- [OpenCV/Tesseract region OCR](osii-tesseract/README.md): text with bounding boxes.
- [Tabular processors](tabular-dataset-processors/README.md): CSV extraction and collection tables.
- [LLM wiki enrichers](llm-wiki-enrichers/README.md): model-backed wiki artifacts.

The launcher prepares an isolated Python environment for each Toolbox project,
registers the running services, and stops them with Ctrl+C. Choose their routes
in Setup and test one document. Starting a service does not invoke a model;
the wiki enrichers need a configured chat connection when used. Native Tesseract
must be installed for OCR.

Set `OSII_START_TOOLBOX=false` in `.env` to leave Toolbox services stopped at
startup. Setup's service controls can start them on demand. Per-tool host
commands remain available for independent deployment. See the
[connection checklist](../docs/operations/runbook-development.md#connect-an-optional-tool-or-your-own-processor)
and [Processor API](../docs/reference/processor-api/index.md).

Container builds, Quay publication, and separate-repository exports are preserved
on `archive/workstation-deployment-2026-11-03` and deferred on main.
