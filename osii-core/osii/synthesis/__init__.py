"""
OSII synthesis package.

This package owns post-extraction, single-document synthesis over canonical OSII bundles.

Responsibilities:
- read extracted text outputs from an OSII document bundle
- apply a synthesis strategy
- write derived synthesis outputs under the document bundle

Current scope:
- synthesis only

Non-responsibilities:
- extraction
- dataset orchestration
- embeddings or vector indexes
- reader/UI concerns

Key entry points:
- Base synthesizer contract: osii.synthesis.file.base
- Dummy synthesizer: osii.synthesis.dummy_synthesizer
"""