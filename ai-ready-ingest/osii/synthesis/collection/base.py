from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CollectionSynthesisState:
    member_objects_seen: int = 0
    input_chars_read: int = 0
    output_chars_written: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class BaseCollectionSynthesizer(ABC):
    name: str = "base_collection"
    display_name: str = "Base Collection Synthesizer"
    description: str = "Abstract collection-level synthesizer."
    version: str = "1.0"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "scope": "collection",
        }

    @abstractmethod
    def synthesize_collection(
        self,
        *,
        osii_store: Path,
        collection_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError