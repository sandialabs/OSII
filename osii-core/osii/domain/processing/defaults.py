"""Deployment defaults for the Intake form; explicit run payloads remain authoritative."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from osii.configuration import load_tools_config, save_tools_config

ENV_FIELDS = {
    'preset': 'OSII_INTAKE_PRESET', 'chunk_size': 'OSII_INTAKE_CHUNK_SIZE',
    'chunk_overlap': 'OSII_INTAKE_CHUNK_OVERLAP', 'synthesizer': 'OSII_INTAKE_SYNTHESIZER',
    'enricher': 'OSII_INTAKE_ENRICHER', 'include_subfolders': 'OSII_INTAKE_INCLUDE_SUBFOLDERS',
    'show_hidden': 'OSII_INTAKE_SHOW_HIDDEN', 'include_patterns': 'OSII_INTAKE_INCLUDE_PATTERNS',
    'exclude_patterns': 'OSII_INTAKE_EXCLUDE_PATTERNS',
}
INTAKE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'preset': {'enum': ['text', 'search', 'summary-search', 'full']},
    'chunk_size': {'type': 'integer', 'minimum': 1},
    'chunk_overlap': {'type': 'integer', 'minimum': 0},
    **{name: {'type': 'boolean' if name in {'include_subfolders', 'show_hidden'} else 'string'}
       for name in ('synthesizer', 'enricher', 'include_subfolders', 'show_hidden', 'include_patterns', 'exclude_patterns')},
}}

PRESETS = [
    {"id": "text", "label": "Read text only", "synthesize": False, "build_embeddings": False, "enrich": False},
    {"id": "search", "label": "Read + semantic search", "synthesize": False, "build_embeddings": True, "enrich": False},
    {"id": "summary-search", "label": "Read + summaries + search", "synthesize": True, "build_embeddings": True, "enrich": False},
    {"id": "full", "label": "Read + summaries + search + enrichment", "synthesize": True, "build_embeddings": True, "enrich": True},
]


def intake_defaults(environment: Mapping[str, str] | None = None, settings: Mapping[str, Any] | None = None) -> dict:
    env = os.environ if environment is None else environment
    env = {**env, **{ENV_FIELDS[name]: str(value) for name, value in (settings or {}).items() if name in ENV_FIELDS}}
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


def configured_intake_defaults() -> dict:
    return intake_defaults(settings=load_tools_config().get('intake', {}))


def save_intake_defaults(settings: dict[str, Any]) -> dict:
    from jsonschema import validate
    validate(settings, INTAKE_SCHEMA)
    configuration = load_tools_config()
    saved = {**configuration.get('intake', {}), **settings}
    value = intake_defaults(settings=saved)  # Validate cross-field chunk constraints before writing.
    configuration['intake'] = saved
    save_tools_config(configuration)
    return value
