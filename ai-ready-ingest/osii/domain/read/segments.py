from pathlib import Path

from osii.domain.read.manifest import (
    get_manifest_record_by_id,
    get_record_path,
    list_text_records,
)


def list_segments(osii_store, file_id: str) -> list[dict]:
    return list_text_records(osii_store, file_id)


def get_segment_record(osii_store, file_id: str, seg: int) -> dict | None:
    seg_id = f"seg-{int(seg):06d}"
    return get_manifest_record_by_id(osii_store, file_id, seg_id)


def _slice_text_by_span(text: str, span: dict) -> str | None:
    if not span:
        return None

    char_start = span.get("char_start")
    char_end = span.get("char_end")

    if char_start is None or char_end is None:
        return None

    try:
        char_start = int(char_start)
        char_end = int(char_end)
    except Exception:
        return None

    if char_start < 0 or char_end < char_start:
        return None

    return text[char_start:char_end]


def get_segment_text(osii_store, file_id: str, seg: int) -> str | None:
    record = get_segment_record(osii_store, file_id, seg)
    if record is None:
        return None

    path = get_record_path(osii_store, file_id, record)
    if path is None:
        return None

    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    span = record.get("span")
    if span:
        sliced = _slice_text_by_span(text, span)
        return sliced if sliced is not None else text

    # backward-compatible: old one-file-per-segment format
    return text