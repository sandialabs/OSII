"""Deployment defaults for the Intake form; explicit run payloads remain authoritative."""
from __future__ import annotations

import os
from collections.abc import Mapping

PRESETS = [
    {"id": "text", "label": "Read text only", "synthesize": False, "build_embeddings": False, "enrich": False},
    {"id": "search", "label": "Read + semantic search", "synthesize": False, "build_embeddings": True, "enrich": False},
    {"id": "summary-search", "label": "Read + summaries + search", "synthesize": True, "build_embeddings": True, "enrich": False},
    {"id": "full", "label": "Read + summaries + search + enrichment", "synthesize": True, "build_embeddings": True, "enrich": True},
]


def intake_defaults(environment: Mapping[str, str] | None = None) -> dict:
    env = os.environ if environment is None else environment
    preset_id = env.get("OSII_INTAKE_PRESET", "summary-search")
    preset = next((p for p in PRESETS if p["id"] == preset_id), None)
    if preset is None:
        raise ValueError("OSII_INTAKE_PRESET must be text, search, summary-search, or full")
    def boolean(name: str, default: bool) -> bool:
        value = env.get(name, str(default)).strip().lower()
        if value not in {"true", "false", "1", "0"}:
            raise ValueError(f"{name} must be true or false")
        return value in {"true", "1"}
    try:
        size = int(env.get("OSII_INTAKE_CHUNK_SIZE", "768"))
        overlap = int(env.get("OSII_INTAKE_CHUNK_OVERLAP", "128"))
    except ValueError:
        raise ValueError("Intake chunk size and overlap must be integers") from None
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Intake chunk size must be positive and overlap must be smaller than size")
    return {
        "preset": preset_id, "presets": PRESETS,
        **{key: preset[key] for key in ("synthesize", "build_embeddings", "enrich")},
        "include_subfolders": boolean("OSII_INTAKE_INCLUDE_SUBFOLDERS", True),
        "show_hidden": boolean("OSII_INTAKE_SHOW_HIDDEN", False),
        "include_patterns": env.get("OSII_INTAKE_INCLUDE_PATTERNS", "").replace(",", "\n"),
        "exclude_patterns": env.get("OSII_INTAKE_EXCLUDE_PATTERNS", "").replace(",", "\n"),
        "chunk_size": size, "chunk_overlap": overlap,
        "synthesizer": env.get("OSII_INTAKE_SYNTHESIZER", ""),
        "enricher": env.get("OSII_INTAKE_ENRICHER", ""),
    }
