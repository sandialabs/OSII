from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EnrichmentState:
    input_objects_seen: int = 0
    input_chars_read: int = 0
    output_files_written: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class BaseEnricher(ABC):
    name: str = "base_enricher"
    display_name: str = "Base Enricher"
    description: str = "Abstract enrichment producer."
    version: str = "1.0"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
        }

    @abstractmethod
    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError