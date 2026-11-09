"""Read-only statistics for an explicit library, folder, or collection scope."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
import json
from pathlib import Path
import tomllib
from typing import Any

import faiss

from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
from osii.domain.artifacts.edited_text import reconstruct_edited_full_text
from osii.domain.artifacts.text_representations import list_text_representations
from osii.domain.model_provider_config import selected_model, selected_processor
from osii.domain.read.docs import get_doc_meta
from osii.domain.read.synthesis import list_syntheses
from osii.domain.scopes.membership import list_scope_file_ids
from osii.indexing.common import embedding_namespace


def _recorded_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _date_histogram(dates: list[datetime], file_count: int) -> dict[str, Any]:
    """Keep chronological, equally spaced bins, including empty intervals."""
    buckets: list[dict[str, Any]] = []
    if dates:
        months = [date.year * 12 + date.month - 1 for date in dates]
        if max(months) - min(months) < 12:
            counts = Counter(months)
            buckets = [
                {"label": f"{month // 12:04d}-{month % 12 + 1:02d}", "count": counts[month]}
                for month in range(min(months), max(months) + 1)
            ]
        else:
            start, end = min(date.year for date in dates), max(date.year for date in dates)
            width = max(1, (end - start + 12) // 12)
            counts = Counter((date.year - start) // width for date in dates)
            buckets = [
                {"label": str(year) if width == 1 else f"{year}–{min(year + width - 1, end)}", "count": counts[(year - start) // width]}
                for year in range(start, end + 1, width)
            ]
    return {
        "recorded_count": len(dates), "missing_count": file_count - len(dates),
        "earliest": min(dates).isoformat() if dates else None,
        "latest": max(dates).isoformat() if dates else None,
        "buckets": buckets,
    }


@lru_cache(maxsize=4)
def _read_semantic_index(directory: str, signature: tuple[tuple[int, int], ...]) -> tuple[dict[str, Any], frozenset[str]]:
    """Cache derived counts, not vectors; any index-file change invalidates them."""
    root = Path(directory)
    try:
        metadata = tomllib.loads((root / "segments.meta.toml").read_text(encoding="utf-8"))["embeddings"]
        if metadata.get("semantic") is not True:
            return {"status": "incompatible", "detail": "This is a lexical compatibility index, not semantic embeddings."}, frozenset()
        index = faiss.read_index(str(root / "segments.faiss"))
        count, dimension = index.ntotal, index.d
        del index
        file_ids: set[str] = set()
        row_count = 0
        with (root / "segments.mapping.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("faiss_id") != row_count or not row.get("file_id"):
                    raise ValueError("The embedding mapping has inconsistent vector identities.")
                file_ids.add(str(row["file_id"]))
                row_count += 1
        if count != row_count or count != metadata.get("count") or dimension != metadata.get("dimension"):
            raise ValueError("Index, vector mapping, and metadata counts or dimensions disagree.")
        return {"status": "ready", "detail": "Saved index and vector mapping validated.", "model": metadata.get("model"), "provider": metadata.get("provider"), "dimensions": dimension}, frozenset(file_ids)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        return {"status": "invalid", "detail": f"Rebuild the semantic index: {exc}"}, frozenset()


def _semantic_index(osii_root: Path) -> tuple[dict[str, Any], frozenset[str]]:
    provider = selected_processor("embedder", osii_root=osii_root)
    model = selected_model("embedder", osii_root=osii_root)
    provider_dir, model_dir = embedding_namespace(model=model, provider=provider)
    directory = osii_root / "embeddings" / "providers" / provider_dir / model_dir
    from osii.domain.storage.embedding_snapshot import active_snapshot
    directory = active_snapshot(directory)
    try:
        signature = tuple(
            (path.stat().st_mtime_ns, path.stat().st_size)
            for path in (directory / "segments.faiss", directory / "segments.mapping.jsonl", directory / "segments.meta.toml")
        )
    except OSError:
        return {"status": "missing", "detail": "Run semantic embeddings in Intake after selecting an embedding model.", "model": model, "provider": provider}, frozenset()
    details, file_ids = _read_semantic_index(str(directory), signature)
    if details["status"] == "ready" and (details.get("model") != model or details.get("provider") != provider):
        return {"status": "incompatible", "detail": "The saved index does not match the selected model connection."}, frozenset()
    return details, file_ids


def get_scope_overview(osii_root: Path, scope: dict) -> dict[str, Any]:
    """Use recorded source metadata and derived artifacts, never browse ambient files."""
    file_ids = list(dict.fromkeys(list_scope_file_ids(osii_root, scope)))
    index, indexed_file_ids = _semantic_index(osii_root)
    sizes: list[int] = []
    created: list[datetime] = []
    modified: list[datetime] = []
    file_types: Counter[str] = Counter()
    text_count = synthesis_count = enrichment_count = indexed_count = missing_metadata = 0
    unreadable: list[str] = []
    for file_id in file_ids:
        # Object identity must remain inside this explicit canonical store.
        if (osii_root / "objects" / file_id).resolve().parent != (osii_root / "objects").resolve():
            missing_metadata += 1
            file_types["Unknown"] += 1
            continue
        try:
            meta = get_doc_meta(osii_root, file_id)
            file = (meta or {}).get("file", {})
            if not meta:
                missing_metadata += 1
            size = file.get("size_bytes")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                sizes.append(size)
            created_date = _recorded_date(file.get("birthtime_utc"))
            modified_date = _recorded_date(file.get("mtime_utc"))
            if created_date:
                created.append(created_date)
            if modified_date:
                modified.append(modified_date)
            filename = str(file.get("filename") or file.get("source_relpath") or "").replace("\\", "/")
            file_types[Path(filename).suffix.lower() or "No extension / unknown"] += 1
            representations = list_text_representations(osii_root, file_id) or []
            has_text = any(
                item.get("preferred") and item.get("exists")
                and (bool(reconstruct_edited_full_text(osii_root, file_id))
                     if item.get("name") == "edited"
                     else (osii_root / item["path"]).stat().st_size > 0)
                for item in representations
            )
            stale = (get_artifact_staleness(osii_root, file_id) or {}).get("stale", {})
            text_count += int(has_text)
            synthesis_count += int(bool(list_syntheses(osii_root, file_id)) and not stale.get("syntheses"))
            enrichments_dir = osii_root / "objects" / file_id / "enrichments"
            has_enrichment = enrichments_dir.is_dir() and any(
                not item.name.endswith(".meta.json") for item in enrichments_dir.iterdir()
            )
            enrichment_count += int(has_enrichment and not stale.get("enrichments"))
            indexed_count += int(has_text and file_id in indexed_file_ids and not stale.get("embeddings") and not stale.get("search_chunks"))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            unreadable.append(f"{file_id}: {exc}")
    return {
        "scope": scope, "file_count": len(file_ids), "size_known_count": len(sizes),
        "total_size_bytes": sum(sizes), "average_size_bytes": sum(sizes) / len(sizes) if sizes else None,
        "missing_metadata_count": missing_metadata,
        "file_types": [{"label": label, "count": count} for label, count in file_types.most_common()],
        "dates": {"created": _date_histogram(created, len(file_ids)), "modified": _date_histogram(modified, len(file_ids))},
        "processing": {"text_count": text_count, "synthesis_count": synthesis_count, "enrichment_count": enrichment_count, "indexed_count": indexed_count, "semantic_index": index},
        "warnings": unreadable,
    }
