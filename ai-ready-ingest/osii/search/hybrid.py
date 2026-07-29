from __future__ import annotations


def reciprocal_rank_fusion(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    merged: dict[tuple[str, str | None], dict] = {}
    scores: dict[tuple[str, str | None], float] = {}

    for result_list in result_lists:
        for rank, item in enumerate(result_list, start=1):
            key = (item.get("file_id"), item.get("chunk_id"))
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)

            if key not in merged:
                merged[key] = item.copy()

    out = []
    for key, item in merged.items():
        item["score"] = scores[key]
        out.append(item)

    out.sort(key=lambda x: (-x["score"], x.get("source_relpath", "")))
    return out