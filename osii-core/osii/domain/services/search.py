from pathlib import Path

from osii.domain.artifacts.text_spans import get_text_by_span
from osii.domain.scopes.collections import list_collections_for_file
from osii.domain.scopes.search import build_scope_filters, file_matches_scope
from osii.domain.read.segments import list_segments
from osii.search.common import search_segments
from osii.search.hybrid import reciprocal_rank_fusion
from osii.search.lexical import lexical_search_chunks


def _safe_snippet(osii_root: Path, file_id: str, char_start, char_end) -> str | None:
    if char_start is None or char_end is None:
        return None

    snippet = get_text_by_span(
        osii_root,
        file_id,
        char_start=char_start,
        char_end=char_end,
    )
    if snippet:
        return snippet[:400].strip()
    return None


def _source_grounding(
    osii_root: Path,
    row: dict,
    char_start: int | None,
    char_end: int | None,
) -> tuple[str | None, int | None, dict]:
    segment_ids = [
        value for value in (row.get("source_segment_ids") or []) if isinstance(value, str)
    ]
    pages = [value for value in (row.get("source_pages") or []) if isinstance(value, int)]
    if not segment_ids and char_start is not None and char_end is not None:
        for segment in list_segments(osii_root, row["file_id"]):
            span = segment.get("span") or {}
            segment_start = span.get("char_start")
            segment_end = span.get("char_end")
            if not isinstance(segment_start, int) or not isinstance(segment_end, int):
                continue
            if char_start >= segment_end or char_end <= segment_start:
                continue
            segment_id = segment.get("id")
            if isinstance(segment_id, str):
                segment_ids.append(segment_id)
            page = (segment.get("source_origin") or {}).get("page")
            if isinstance(page, int) and page not in pages:
                pages.append(page)

    source_origin = {
        "grounding_type": "text_span",
        "char_start": char_start,
        "char_end": char_end,
        "segment_ids": segment_ids,
        "pages": pages,
        "overlap_with_previous": row.get("overlap_with_previous", 0),
    }
    return (
        segment_ids[0] if segment_ids else None,
        pages[0] if pages else None,
        source_origin,
    )


def _suppress_redundant_overlaps(results: list[dict], *, top_k: int) -> list[dict]:
    selected: list[dict] = []
    for candidate in results:
        start = candidate.get("char_start")
        end = candidate.get("char_end")
        redundant = False
        if isinstance(start, int) and isinstance(end, int) and end > start:
            for existing in selected:
                if existing.get("file_id") != candidate.get("file_id"):
                    continue
                other_start = existing.get("char_start")
                other_end = existing.get("char_end")
                if not isinstance(other_start, int) or not isinstance(other_end, int):
                    continue
                overlap = max(0, min(end, other_end) - max(start, other_start))
                shorter = min(end - start, other_end - other_start)
                if shorter > 0 and overlap / shorter >= 0.65:
                    redundant = True
                    break
        if not redundant:
            selected.append(candidate)
        if len(selected) >= top_k:
            break
    return selected


def _lexical_candidates(
    osii_root: Path,
    query: str,
    *,
    top_k: int,
    scope: dict | None = None,
) -> list[dict]:
    scope_filters = build_scope_filters(osii_root, scope)
    rows = lexical_search_chunks(osii_root, query, top_k=max(top_k * 5, top_k))
    results = []

    for row in rows:
        file_id = row["file_id"]
        source_relpath = row.get("source_relpath", "")

        if not file_matches_scope(
            file_id=file_id,
            source_relpath=source_relpath,
            scope_filters=scope_filters,
        ):
            continue

        char_start = row.get("char_start")
        char_end = row.get("char_end")
        snippet = _safe_snippet(osii_root, file_id, char_start, char_end)
        segment_id, page, source_origin = _source_grounding(
            osii_root, row, char_start, char_end
        )

        results.append(
            {
                "file_id": file_id,
                "filename": source_relpath.split("/")[-1],
                "source_relpath": source_relpath,
                "snippet": snippet,
                "score": row["score"],
                "match_type": "lexical",
                "chunk_id": row.get("chunk_id"),
                "chunk_method": row.get("chunk_method"),
                "chunk_index": row.get("chunk_index"),
                "segment_id": segment_id,
                "page": page,
                "char_start": char_start,
                "char_end": char_end,
                "source_text_representation": row.get("source_text_representation"),
                "source_text_kind": row.get("source_text_kind"),
                "source_origin": source_origin,
                "collections": list_collections_for_file(osii_root, file_id),
            }
        )

    results.sort(key=lambda r: (-r["score"], r["source_relpath"]))
    return results[:max(top_k * 5, top_k)]


def _semantic_candidates(
    osii_root: Path,
    query: str,
    top_k: int,
    *,
    scope: dict | None = None,
) -> list[dict]:
    scope_filters = build_scope_filters(osii_root, scope)

    rows = search_segments(osii_root, query, top_k=max(top_k * 5, top_k))
    results = []

    for row in rows:
        file_id = row["file_id"]
        source_relpath = row.get("source_relpath", "")

        if not file_matches_scope(
            file_id=file_id,
            source_relpath=source_relpath,
            scope_filters=scope_filters,
        ):
            continue

        char_start = row.get("char_start")
        char_end = row.get("char_end")
        snippet = _safe_snippet(osii_root, file_id, char_start, char_end)
        segment_id, page, source_origin = _source_grounding(
            osii_root, row, char_start, char_end
        )

        results.append(
            {
                "file_id": file_id,
                "filename": source_relpath.split("/")[-1],
                "source_relpath": source_relpath,
                "snippet": snippet,
                "score": row["score"],
                "match_type": "semantic",
                "chunk_id": row.get("chunk_id"),
                "chunk_method": row.get("chunk_method"),
                "chunk_index": row.get("chunk_index"),
                "segment_id": segment_id,
                "page": page,
                "char_start": char_start,
                "char_end": char_end,
                "source_text_representation": row.get("source_text_representation"),
                "source_text_kind": row.get("source_text_kind"),
                "source_origin": source_origin,
                "collections": list_collections_for_file(osii_root, file_id),
            }
        )

    results.sort(key=lambda r: (-r["score"], r["source_relpath"]))
    return results[:max(top_k * 5, top_k)]


def _group_results_by_file(results: list[dict], *, top_k: int) -> list[dict]:
    best_by_file: dict[str, dict] = {}

    for item in results:
        file_id = item["file_id"]
        existing = best_by_file.get(file_id)
        if existing is None or item["score"] > existing["score"]:
            best_by_file[file_id] = item

    grouped = list(best_by_file.values())
    grouped.sort(key=lambda r: (-r["score"], r["source_relpath"]))
    return grouped[:top_k]


def dashboard_search(
    osii_root: Path,
    *,
    query: str,
    mode: str,
    top_k: int = 10,
    scope: dict | None = None,
    group_by: str | None = None,
) -> tuple[str, list[dict]]:
    mode = mode.strip().lower()
    if mode not in {"semantic", "lexical", "hybrid"}:
        raise ValueError(f"Unsupported search mode: {mode}")

    retrieval_mode_used = mode

    if mode == "semantic":
        results = _semantic_candidates(
            osii_root,
            query,
            top_k=top_k,
            scope=scope,
        )

    elif mode == "lexical":
        results = _lexical_candidates(
            osii_root,
            query,
            top_k=top_k,
            scope=scope,
        )

    else:
        try:
            sem = _semantic_candidates(
                osii_root,
                query,
                top_k=top_k,
                scope=scope,
            )
        except Exception:
            sem = []

        lex = _lexical_candidates(
            osii_root,
            query,
            top_k=top_k,
            scope=scope,
        )

        if not sem:
            retrieval_mode_used = "lexical"
            for item in lex:
                item["match_type"] = "hybrid"
            results = lex
        else:
            fused = reciprocal_rank_fusion([sem, lex])
            for item in fused:
                item["match_type"] = "hybrid"
            results = fused

    results = _suppress_redundant_overlaps(results, top_k=top_k)

    if (group_by or "").strip().lower() == "file":
        results = _group_results_by_file(results, top_k=top_k)

    return retrieval_mode_used, results
