# OSII processor modules

Optional processor implementations live in this repository. They receive explicit
Processor API requests and return typed results; Core owns persistence. They do
not start automatically with `make dev`.

- [OpenCV/Tesseract region OCR](osii-tesseract/README.md): text with bounding boxes.
- [Tabular processors](tabular-dataset-processors/README.md): CSV extraction and collection tables.
- [LLM wiki enrichers](llm-wiki-enrichers/README.md): model-backed wiki artifacts.

Use the per-tool host commands and isolated Python environments. Register the
running service URL in Setup, choose its route, and test one document. See the
[connection checklist](../docs/operations/runbook-development.md#connect-an-optional-tool-or-your-own-processor)
and [Processor API](../docs/reference/processor-api/index.md).

Container builds, Quay publication, and separate-repository exports are preserved
on `archive/workstation-deployment-2026-11-03` and deferred on main.

Frontend tools belong to the dashboard **Toolbox**. This directory contains independently deployed backend **processors**, each implementing an OSII Processor API component.
