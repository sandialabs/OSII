from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FolderSynthesisState:
    child_object_synthesis_seen: int = 0
    child_folder_synthesis_seen: int = 0
    fallback_text_records_seen: int = 0
    input_chars_read: int = 0
    output_chars_written: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class BaseFolderSynthesizer(ABC):
    name: str = "base_folder"
    display_name: str = "Base Folder Synthesizer"
    description: str = "Abstract folder-level synthesizer."
    version: str = "1.0"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "scope": "folder",
        }

    @abstractmethod
    def synthesize_folder(
        self,
        *,
        osii_store: Path,
        folder_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError