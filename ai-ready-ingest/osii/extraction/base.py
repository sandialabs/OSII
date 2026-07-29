from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ExtractionSegment:
    seg: int
    type: str
    text: str | None = None
    source_origin: dict[str, Any] = field(default_factory=dict)
    related_ids: list[str] = field(default_factory=list)


@dataclass
class ExtractionArtifact:
    artifact_id: str
    kind: str
    type: str
    extension: str
    data: bytes
    source_origin: dict[str, Any]
    related_ids: list[str] = field(default_factory=list)


@dataclass
class ExtractionState:
    # remove the segments_written
    segments_written: int = 0
    artifacts_written: int = 0
    units_attempted: int = 0
    units_completed: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class DocumentExtractor(Protocol):
    """Capability contract for a document-to-OSII extraction implementation."""

    def extract(
        self,
        *,
        source_path: Path,
        data_volume_root: Path,
        osii_store: Path,
        expert_context: str | None = None,
        extractor_config: dict | None = None,
    ) -> dict: ...


class BaseExtractor(ABC):
    name: str = "base"
    version: str = "1.0"
    display_name: str = "Base Extractor"
    description: str = "Abstract extractor."

    @abstractmethod
    def extract(
        self,
        *,
        source_path: Path,
        data_volume_root: Path,
        osii_store: Path,
        expert_context: str | None = None,
        extractor_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError
    
    def describe(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
        }
