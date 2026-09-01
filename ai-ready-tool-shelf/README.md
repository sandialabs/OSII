# AI-Ready Tool Shelf

Optional, customized external tools and runtimes used by the main application.
Each directory is intended to be understandable, buildable, and publishable as
its own repository in a corporate environment.

Examples:
- a standalone embedder or LLM service
- a domain-specific utility that does not belong in the recommended model tool chest.

This directory keeps tool-specific setup and configuration separate from core
application code. A generic custom extractor, synthesizer, embedder, or
enricher should implement OSII Processor API v1 through
`osii-processor-sdk`; a specialty tool may retain its own API when OSII has a
documented adapter boundary.
