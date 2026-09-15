"""Deprecated import shim for the optional readable-wiki Processor API service.

The wiki implementation lives in ``osii-toolbox/llm-wiki-enrichers``. This
module retains an old Python import without registering or implementing a wiki
inside Core.
"""

from __future__ import annotations

from pathlib import Path
import warnings

from osii.processors.remote import RemoteEnricher, resolve_remote_processor


class LlmWikiEnricher:
    """Delegate the legacy class name to ``toolbox.readable-wiki``."""

    name = "toolbox.readable-wiki"

    def __init__(self) -> None:
        warnings.warn(
            "LlmWikiEnricher moved to the optional toolbox.readable-wiki "
            "Processor API service; register that service and use RemoteEnricher.",
            DeprecationWarning,
            stacklevel=2,
        )

    def describe(self) -> dict:
        return resolve_remote_processor(self.name, "enricher")

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        descriptor = resolve_remote_processor(self.name, "enricher")
        return RemoteEnricher(descriptor).enrich(
            osii_store=osii_store,
            scope=scope,
            expert_context=expert_context,
            enricher_config=enricher_config,
        )
