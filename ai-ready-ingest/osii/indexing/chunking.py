from __future__ import annotations

from pathlib import Path
import json
import re

from osii.domain.read.catalog import load_files_catalog
from osii.domain.read.segments import list_segments
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.storage.store import embeddings_chunks_manifest_path


DEFAULT_CHUNKING_METHOD = "sentence_window"
DEFAULT_CHUNK_SIZE = 768
DEFAULT_CHUNK_OVERLAP = 128
SUPPORTED_CHUNKING_METHODS = ("sentence_window", "paragraph", "window")


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in re.finditer(r"\S(?:.*?\S)?(?:\n\s*\n|$)", text, flags=re.DOTALL):
        start, end = match.span()
        chunk = text[start:end].strip()
        if chunk:
            trimmed_start = text.find(chunk, start, end)
            trimmed_end = trimmed_start + len(chunk)
            spans.append((trimmed_start, trimmed_end))
    return spans


def _window_spans(text: str, chunk_size: int, overlap: int) -> list[tuple[int, int]]:
    spans = []
    start = 0
    step = max(1, chunk_size - overlap)

    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            trimmed_start = text.find(chunk, start, end)
            trimmed_end = trimmed_start + len(chunk)
            spans.append((trimmed_start, trimmed_end))
        if end >= len(text):
            break
        start += step

    return spans


def validate_chunking_settings(method: str, chunk_size: int, overlap: int) -> None:
    if method not in SUPPORTED_CHUNKING_METHODS:
        raise ValueError(f"Unsupported chunking method: {method}")
    if method == "paragraph":
        return
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0:
        raise ValueError("chunk_overlap must be zero or greater")
    if overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")


def _boundary_positions(text: str) -> tuple[list[int], list[int]]:
    paragraph_boundaries = [match.start() for match in re.finditer(r"\n\s*\n", text)]
    sentence_boundaries = [
        match.end()
        for match in re.finditer(r"[.!?](?:[\"')\]]+)?(?=\s|$)", text)
    ]
    return paragraph_boundaries, sentence_boundaries


def _last_boundary_between(boundaries: list[int], lower: int, upper: int) -> int | None:
    candidates = [value for value in boundaries if lower <= value <= upper]
    return candidates[-1] if candidates else None


def _structured_window_spans(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[tuple[int, int]]:
    """Build sentence/paragraph-aligned windows while retaining exact offsets."""
    validate_chunking_settings("sentence_window", chunk_size, overlap)
    paragraph_boundaries, sentence_boundaries = _boundary_positions(text)
    all_boundaries = sorted(set([*paragraph_boundaries, *sentence_boundaries]))
    spans: list[tuple[int, int]] = []
    start = 0

    while start < len(text):
        while start < len(text) and text[start].isspace():
            start += 1
        if start >= len(text):
            break

        hard_end = min(len(text), start + chunk_size)
        end = hard_end
        if hard_end < len(text):
            useful_minimum = start + max(1, chunk_size // 2)
            end = (
                _last_boundary_between(paragraph_boundaries, useful_minimum, hard_end)
                or _last_boundary_between(sentence_boundaries, useful_minimum, hard_end)
            )
            if end is None:
                whitespace = text.rfind(" ", useful_minimum, hard_end + 1)
                end = whitespace if whitespace > start else hard_end

        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            end = hard_end
        spans.append((start, end))
        if end >= len(text):
            break

        desired_start = max(start + 1, end - overlap)
        # Prefer a nearby structural boundary without allowing one unusually
        # long sentence to turn the next window into a near-duplicate.
        boundary_floor = max(start + 1, desired_start - overlap)
        next_start = _last_boundary_between(all_boundaries, boundary_floor, desired_start)
        if next_start is None:
            whitespace = text.rfind(" ", boundary_floor, desired_start + 1)
            next_start = whitespace if whitespace > start else desired_start
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start if next_start > start else min(end, start + 1)

    return spans


def _chunk_source_grounding(
    segments: list[dict],
    char_start: int,
    char_end: int,
) -> tuple[list[str], list[int]]:
    segment_ids: list[str] = []
    pages: list[int] = []
    for segment in segments:
        span = segment.get("span") or {}
        segment_start = span.get("char_start")
        segment_end = span.get("char_end")
        if not isinstance(segment_start, int) or not isinstance(segment_end, int):
            continue
        if char_start >= segment_end or char_end <= segment_start:
            continue
        segment_id = segment.get("id")
        if isinstance(segment_id, str) and segment_id not in segment_ids:
            segment_ids.append(segment_id)
        page = (segment.get("source_origin") or {}).get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
    return segment_ids, pages


def generate_chunk_records(
    osii_root: Path,
    *,
    method: str = DEFAULT_CHUNKING_METHOD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    validate_chunking_settings(method, chunk_size, overlap)
    files = sorted(load_files_catalog(osii_root), key=lambda x: str(x.get("source_relpath", "")).lower())
    rows = []

    for entry in files:
        file_id = entry.get("file_id")
        source_relpath = entry.get("source_relpath", "")
        if not file_id:
            continue

        preferred = get_preferred_text_representation(osii_root, file_id)
        if preferred is None:
            continue

        text = preferred.get("text") or ""
        if not text.strip():
            continue

        if method == "paragraph":
            spans = _paragraph_spans(text)
        elif method == "sentence_window":
            spans = _structured_window_spans(text, chunk_size=chunk_size, overlap=overlap)
        elif method == "window":
            spans = _window_spans(text, chunk_size=chunk_size, overlap=overlap)

        grounded_segments = (
            list_segments(osii_root, file_id)
            if preferred["kind"] == "canonical_extracted_text"
            else []
        )
        file_rows = []

        for i, (char_start, char_end) in enumerate(spans, start=1):
            chunk_text = text[char_start:char_end]
            source_segment_ids, source_pages = _chunk_source_grounding(
                grounded_segments,
                char_start,
                char_end,
            )
            file_rows.append(
                {
                    "chunk_id": f"chunk-{file_id}-{i:06d}",
                    "file_id": file_id,
                    "source_relpath": source_relpath,
                    "source_text_representation": preferred["name"],
                    "source_text_kind": preferred["kind"],
                    "source_extraction_id": preferred.get("extraction_id"),
                    "chunk_method": method,
                    "chunk_index": i,
                    "char_start": char_start,
                    "char_end": char_end,
                    "chunk_size": chunk_size,
                    "chunk_overlap": overlap if method != "paragraph" else 0,
                    "source_segment_ids": source_segment_ids,
                    "source_pages": source_pages,
                    "text": chunk_text,
                }
            )

        for index, row in enumerate(file_rows):
            previous = file_rows[index - 1] if index > 0 else None
            following = file_rows[index + 1] if index + 1 < len(file_rows) else None
            row["previous_chunk_id"] = previous["chunk_id"] if previous else None
            row["next_chunk_id"] = following["chunk_id"] if following else None
            row["overlap_with_previous"] = (
                max(0, previous["char_end"] - row["char_start"])
                if previous
                else 0
            )
        rows.extend(file_rows)

    return rows


def write_chunk_manifest(
    osii_root: Path,
    *,
    method: str = DEFAULT_CHUNKING_METHOD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[Path, list[dict]]:
    rows = generate_chunk_records(
        osii_root,
        method=method,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    path = embeddings_chunks_manifest_path(osii_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        path.unlink()

    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            try:
                line = json.dumps(row, ensure_ascii=False)
            except Exception as exc:
                raise RuntimeError(f"Could not serialize chunk row {row.get('chunk_id')}: {exc}") from exc
            f.write(line)
            f.write("\n")

    return path, rows
