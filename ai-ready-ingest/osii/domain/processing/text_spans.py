from __future__ import annotations

from pathlib import Path

from osii.domain.storage.store import object_text_path


def get_text_by_span(
    osii_root: Path,
    file_id: str,
    *,
    char_start: int,
    char_end: int,
) -> str | None:
    path = object_text_path(osii_root, file_id)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    try:
        char_start = int(char_start)
        char_end = int(char_end)
    except Exception:
        return None

    if char_start < 0 or char_end < char_start:
        return None

    if char_start > len(text):
        return None

    char_end = min(char_end, len(text))
    return text[char_start:char_end]


def get_text_context_by_span(
    osii_root: Path,
    file_id: str,
    *,
    char_start: int,
    char_end: int,
    context_chars: int = 200,
) -> dict | None:
    path = object_text_path(osii_root, file_id)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")

    try:
        char_start = int(char_start)
        char_end = int(char_end)
        context_chars = int(context_chars)
    except Exception:
        return None

    if char_start < 0 or char_end < char_start:
        return None

    if char_start > len(text):
        return None

    char_end = min(char_end, len(text))
    left_start = max(0, char_start - context_chars)
    right_end = min(len(text), char_end + context_chars)

    return {
        "file_id": file_id,
        "char_start": char_start,
        "char_end": char_end,
        "match_text": text[char_start:char_end],
        "before_text": text[left_start:char_start],
        "after_text": text[char_end:right_end],
        "window_start": left_start,
        "window_end": right_end,
    }