from __future__ import annotations

from pathlib import Path
import tomllib

from osii.domain.artifacts.edited_text import edited_text_path
from osii.domain.artifacts.extraction_variants import list_extraction_variants, primary_extraction_dir
from osii.domain.storage.store import object_text_path, provenance_path
from osii.extraction.registry import get_extractors
from osii.synthesis.registry import get_synthesizers


def _registry_name_map(items) -> dict:
    out = {}
    for item in items:
        out[item.name] = item.describe()
    return out


def _read_provenance(osii_root: Path, file_id: str) -> dict | None:
    path = provenance_path(osii_root, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def get_object_processing_metadata(osii_root: Path, file_id: str) -> dict | None:
    obj_dir = (osii_root / "objects" / file_id).resolve()
    if not obj_dir.exists():
        return None

    prov = _read_provenance(osii_root, file_id) or {}

    extractor_map = _registry_name_map(get_extractors())
    synthesizer_map = _registry_name_map(get_synthesizers())

    extractor_name = prov.get("extractor", {}).get("name")
    synthesizer_name = prov.get("synthesis", {}).get("name")

    extractor_display = extractor_map.get(extractor_name, {}).get("display_name") if extractor_name else None
    synthesizer_display = synthesizer_map.get(synthesizer_name, {}).get("display_name") if synthesizer_name else None

    extraction_state = list_extraction_variants(osii_root, file_id) or {}
    primary_dir = primary_extraction_dir(osii_root, file_id)
    canonical_text = (primary_dir / "text.txt") if primary_dir else object_text_path(osii_root, file_id)
    edited_text = edited_text_path(osii_root, file_id)

    supports_markdown_render = extractor_name in {"pdf_default", "banyan_ingest", "banyan-extract", "banyan"}
    supports_text_editing = canonical_text.exists()

    return {
        "extractor": {
            "name": extractor_name,
            "display_name": extractor_display,
        },
        "extractions": extraction_state,
        "synthesizer": {
            "name": synthesizer_name,
            "display_name": synthesizer_display,
        },
        "canonical_text_path": (
            f"objects/{file_id}/text.txt" if canonical_text.exists() else None
        ),
        "editable_text_path": (
            f"objects/{file_id}/edited_text.json" if edited_text.exists() else None
        ),
        "has_editable_text": edited_text.exists(),
        "capabilities": {
            "supports_markdown_render": supports_markdown_render,
            "supports_text_editing": supports_text_editing,
        },
    }
