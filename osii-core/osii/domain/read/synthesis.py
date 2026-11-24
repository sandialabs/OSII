from pathlib import Path
import json
import tomllib

from osii.domain.storage.store import object_dir, object_synth_path, object_synth_toml_path


def get_synth_text(osii_store: Path, file_id: str) -> str | None:
    path = object_synth_path(osii_store, file_id)
    from osii.domain.artifacts.products import read_product
    data = read_product(path)["data"]
    return data["text"] if data is not None else None


def get_synth_toml(osii_store: Path, file_id: str) -> dict | None:
    path = object_synth_toml_path(osii_store, file_id)
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def list_syntheses(osii_store: Path, file_id: str) -> list[dict]:
    txt_path = object_synth_path(osii_store, file_id)
    toml_path = object_synth_toml_path(osii_store, file_id)

    if not txt_path.exists() and not toml_path.exists():
        return []

    return [
        {
            "name": "current",
            "text_path": str(txt_path) if txt_path.exists() else None,
            "toml_path": str(toml_path) if toml_path.exists() else None,
            "scope": "object",
        }
    ]


def get_suggested_metadata(osii_store: Path, file_id: str) -> dict:
    """Current derived suggestions; old extraction outputs never label new text."""
    from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
    from osii.domain.storage.store import provenance_path
    from osii.domain.document_metadata import METADATA_ENRICHER, synthesis_labels
    try:
        from osii.domain.document_metadata import read_manual_metadata
        _, manual = read_manual_metadata(osii_store, file_id)
        if manual is not None:
            return synthesis_labels({"document_metadata": manual})
        stale = (get_artifact_staleness(osii_store, file_id) or {}).get("stale", {})
        if not stale.get("document_metadata", stale.get("enrichments")):
            path = object_dir(osii_store, file_id) / "enrichments" / f"document_metadata--{METADATA_ENRICHER}.json"
            if path.is_file():
                try:
                    metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
                    suggestions = synthesis_labels(metadata) if isinstance(metadata, dict) else {}
                    if suggestions.get("document_metadata"):
                        return suggestions
                except (OSError, ValueError, TypeError):
                    pass
        if stale.get("syntheses"):
            return {}
        provenance = tomllib.loads(provenance_path(osii_store, file_id).read_text(encoding="utf-8"))
        return synthesis_labels(provenance.get("synthesis", {}).get("config", {}))
    except (OSError, ValueError, TypeError):
        return {}
