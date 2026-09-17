from pathlib import Path
import tomllib

from osii.domain.storage.store import object_dir
from osii.domain.read.manifest import list_image_records, list_text_records
from osii.domain.read.synthesis import get_synth_text


def get_doc_dir(osii_store: Path, file_id: str) -> Path:
    return object_dir(osii_store, file_id).resolve()


def get_doc_meta(osii_store: Path, file_id: str) -> dict | None:
    path = get_doc_dir(osii_store, file_id) / "meta.toml"
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def get_doc_overview(osii_store: Path, file_id: str) -> dict:
    meta = get_doc_meta(osii_store, file_id)
    text_items = list_text_records(osii_store, file_id)
    image_items = list_image_records(osii_store, file_id)
    synth_text = get_synth_text(osii_store, file_id)

    return {
        "file_id": file_id,
        "meta": meta,
        "text_count": len(text_items),
        "image_count": len(image_items),
        "has_synth": synth_text is not None,
        "text_items": text_items,
        "image_items": image_items,
    }