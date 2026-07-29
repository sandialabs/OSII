from pathlib import Path

from osii.domain.artifacts.text_spans import get_text_by_span
from osii.domain.scopes.collections import list_collections_for_file
from osii.domain.scopes.search import build_scope_filters, file_matches_scope
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
                "page": None,
                "char_start": char_start,
                "char_end": char_end,
                "source_text_representation": row.get("source_text_representation"),
                "source_text_kind": row.get("source_text_kind"),
                "source_origin": {
                    "grounding_type": "text_span",
                    "char_start": char_start,
                    "char_end": char_end,
                },
                "collections": list_collections_for_file(osii_root, file_id),
            }
        )

    results.sort(key=lambda r: (-r["score"], r["source_relpath"]))
    return results[:top_k]


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
                "page": None,
                "char_start": char_start,
                "char_end": char_end,
                "source_text_representation": row.get("source_text_representation"),
                "source_text_kind": row.get("source_text_kind"),
                "source_origin": {
                    "grounding_type": "text_span",
                    "char_start": char_start,
                    "char_end": char_end,
                },
                "collections": list_collections_for_file(osii_root, file_id),
            }
        )

    results.sort(key=lambda r: (-r["score"], r["source_relpath"]))
    return results[:top_k]


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
            results = lex[:top_k]
        else:
            fused = reciprocal_rank_fusion([sem, lex])
            for item in fused:
                item["match_type"] = "hybrid"
            results = fused[:top_k]

    if (group_by or "").strip().lower() == "file":
        results = _group_results_by_file(results, top_k=top_k)

    return retrieval_mode_used, results