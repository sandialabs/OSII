from pathlib import Path
import tomli_w

from osii.domain.storage.store import (
    folder_overview_path,
    folder_synth_text_path,
    folder_synth_toml_path,
    folder_synth_path,
    image_synth_text_path,
    image_synth_toml_path,
    object_synth_text_path,
    object_synth_toml_path,
    root_overview_path,
    root_synth_text_path,
    root_synth_toml_path,
)


def write_object_synth(
    osii_root: Path,
    file_id: str,
    *,
    source_relpath: str,
    synthesis: str,
    doc_type: str,
    quality: str = "default",
    description: str | None = None,
) -> tuple[Path, Path]:
    toml_path = object_synth_toml_path(osii_root, file_id)
    txt_path = object_synth_text_path(osii_root, file_id)

    payload = {
        "path": {
            "source_relpath": source_relpath,
        },
        "synthesis": {
            "synthesis": synthesis,
            "doc_type": doc_type,
            "quality": quality,
        },
    }

    if description:
        payload["details"] = {
            "description": description,
        }

    toml_path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    txt_path.write_text(description or synthesis, encoding="utf-8")
    return toml_path, txt_path


def write_image_synth(
    osii_root: Path,
    file_id: str,
    image: str,
    *,
    source_path: str,
    synthesis: str,
    image_type: str,
    quality: str = "default",
    description: str | None = None,
) -> tuple[Path, Path]:
    toml_path = image_synth_toml_path(osii_root, file_id, image)
    txt_path = image_synth_text_path(osii_root, file_id, image)

    payload = {
        "path": {
            "source_path": source_path,
        },
        "synthesis": {
            "synthesis": synthesis,
            "image_type": image_type,
            "quality": quality,
        },
    }

    if description:
        payload["details"] = {
            "description": description,
        }

    toml_path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    txt_path.write_text(description or synthesis, encoding="utf-8")
    return toml_path, txt_path


def write_folder_overview(osii_root: Path, folder_id: str, payload: dict) -> Path:
    path = folder_overview_path(osii_root, folder_id)
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


def write_folder_synth(
    osii_root: Path,
    folder_id: str,
    *,
    synthesis: str,
    kind: str,
    quality: str = "default",
    description: str | None = None,
) -> tuple[Path, Path]:
    toml_path = folder_synth_toml_path(osii_root, folder_id)
    txt_path = folder_synth_text_path(osii_root, folder_id)

    payload = {
        "synthesis": {
            "synthesis": synthesis,
            "kind": kind,
            "quality": quality,
        }
    }

    if description:
        payload["details"] = {
            "description": description,
        }

    toml_path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    txt_path.write_text(description or synthesis, encoding="utf-8")
    return toml_path, txt_path


def write_root_overview(osii_root: Path, payload: dict) -> Path:
    path = root_overview_path(osii_root)
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


def write_root_synth(
    osii_root: Path,
    *,
    synthesis: str,
    kind: str,
    quality: str = "default",
    description: str | None = None,
) -> tuple[Path, Path]:
    toml_path = root_synth_toml_path(osii_root)
    txt_path = root_synth_text_path(osii_root)

    payload = {
        "synthesis": {
            "synthesis": synthesis,
            "kind": kind,
            "quality": quality,
        }
    }

    if description:
        payload["details"] = {
            "description": description,
        }

    toml_path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    txt_path.write_text(description or synthesis, encoding="utf-8")
    return toml_path, txt_path

def write_folder_synth_text(
    *,
    osii_store: Path,
    folder_id: str,
    text: str,
) -> Path:
    path = folder_synth_path(osii_store, folder_id)
    path.write_text(text, encoding="utf-8")
    return path