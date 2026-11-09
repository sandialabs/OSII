"""Storage-independent cache identity and safe hydration of topic-map geometry."""

from __future__ import annotations
import hashlib
import json
import math
from osii.domain.document_metadata import document_labels

CACHE_VERSION = "pca-map-v1"


def topic_cache_key(identity: object, documents: list[dict], limit: int) -> str:
    return hashlib.sha256(
        json.dumps(
            [CACHE_VERSION, identity, sorted(d["file_id"] for d in documents), limit],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def pack_topic_map(result: dict) -> dict:
    return {
        **{
            key: result[key]
            for key in (
                "index",
                "scope_count",
                "indexed_count",
                "stale_count",
                "unindexed_count",
                "shown_count",
                "projection",
                "explained_variance",
            )
        },
        "points": [
            {key: point[key] for key in ("file_id", "chunk_count", "x", "y")}
            for point in result["points"]
        ],
    }


def hydrate_topic_map(cached: dict | None, documents: list[dict]) -> dict | None:
    if not isinstance(cached, dict):
        return None
    headers = {doc["file_id"]: document_labels(doc) for doc in documents}
    try:
        required = {
            "index",
            "scope_count",
            "indexed_count",
            "stale_count",
            "unindexed_count",
            "shown_count",
            "projection",
            "explained_variance",
            "points",
        }
        if not required.issubset(cached) or not isinstance(cached["index"], dict):
            return None
        counts = [
            cached[key]
            for key in (
                "scope_count",
                "indexed_count",
                "stale_count",
                "unindexed_count",
                "shown_count",
            )
        ]
        if any(type(count) is not int or count < 0 for count in counts):
            return None
        if (
            cached["indexed_count"] + cached["stale_count"] + cached["unindexed_count"]
            != len(documents)
            or cached["shown_count"] > cached["indexed_count"]
        ):
            return None
        points = cached["points"]
        if (
            cached["projection"] != "pca"
            or cached["scope_count"] != len(documents)
            or not isinstance(points, list)
            or len(points) > 500
            or len(points) != cached["shown_count"]
            or len({p["file_id"] for p in points}) != len(points)
            or not math.isfinite(cached["explained_variance"])
        ):
            return None
        hydrated = []
        for point in points:
            if point["file_id"] not in headers or not all(
                math.isfinite(point[axis]) for axis in ("x", "y")
            ):
                return None
            hydrated.append({**point, **headers[point["file_id"]]})
        return {**cached, "points": hydrated}
    except (KeyError, TypeError, ValueError):
        return None
