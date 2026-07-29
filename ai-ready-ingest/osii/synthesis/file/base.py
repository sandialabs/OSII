from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SynthesisState:
    text_records_seen: int = 0
    text_chars_read: int = 0
    output_chars_written: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class BaseSynthesizer(ABC):
    name: str = "base"
    display_name: str = "Base synthesizer"
    description: str = "Abstract synthesizer."
    version: str = "1.0"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
        }

    @abstractmethod
    def synthesize(
        self,
        *,
        osii_store: Path,
        file_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError