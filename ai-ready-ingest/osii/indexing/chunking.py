from __future__ import annotations

from pathlib import Path
import json
import re

from osii.domain.read.catalog import load_files_catalog
from osii.domain.artifacts.text_representations import get_preferred_text_representation
from osii.domain.storage.store import embeddings_chunks_manifest_path


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


def generate_chunk_records(
    osii_root: Path,
    *,
    method: str = "paragraph",
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[dict]:
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
        elif method == "window":
            spans = _window_spans(text, chunk_size=chunk_size, overlap=overlap)
        else:
            raise ValueError(f"Unsupported chunking method: {method}")

        for i, (char_start, char_end) in enumerate(spans, start=1):
            chunk_text = text[char_start:char_end]
            rows.append(
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
                    "text": chunk_text,
                }
            )

    return rows


def write_chunk_manifest(
    osii_root: Path,
    *,
    method: str = "paragraph",
    chunk_size: int = 1200,
    overlap: int = 200,
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
