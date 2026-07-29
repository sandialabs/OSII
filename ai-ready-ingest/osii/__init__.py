"""
OSII extraction package.

This package owns file-by-file extraction into canonical OSII document bundles.

Responsibilities:
- process one source file at a time
- call backend extraction tools or model endpoints
- write canonical extraction outputs:
  - meta.toml
  - provenance.toml
  - manifest.jsonl
  - segments/
  - artifacts/

Non-responsibilities:
- dataset orchestration
- run management
- UI/dashboard concerns
- synthesis
- embeddings or vector indexes

Key entry points:
- Base extractor contract: osii.extraction.base
- Dispatcher: osii.extraction.dispatcher.dispatch_extract
- Single-file CLI: python -m osii.extraction.cli
"""