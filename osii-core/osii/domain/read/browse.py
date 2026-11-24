"""Page one level of the stored document paths without opening originals."""

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Literal

from osii.domain.catalog_db import catalog_path, connect_catalog, ensure_catalog


BrowseSort = Literal["name-asc", "name-desc", "modified-desc", "size-desc"]
SORT_ORDER = {
    "name-asc": "lower(name)",
    "name-desc": "lower(name) DESC",
    "modified-desc": "CASE WHEN mtime_utc IS NULL THEN 1 ELSE 0 END, mtime_utc DESC, lower(name)",
    "size-desc": "CASE WHEN size_bytes IS NULL THEN 1 ELSE 0 END, size_bytes DESC, lower(name)",
}


def _sidecar_rows(root: Path, statement: str, values: dict) -> list[dict]:
    with closing(connect_catalog(root)) as connection:
        return [dict(row) for row in connection.execute(statement, values)]


def browse_catalog(
    root: Path, *, path: str, query: str, sort: BrowseSort, limit: int, offset: int, postgres=None,
) -> dict:
    path = "/".join(part for part in path.replace("\\", "/").split("/") if part and part != ".")
    prefix = path + "/" if path else ""
    # The LIKE bound can use the catalog's case-insensitive index. The exact
    # prefix check keeps separate case-sensitive folders (such as A and a) apart.
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    position = "strpos" if postgres is not None else "instr"
    columns = (
        "media_type AS mime, size_bytes, metadata->'file'->>'mtime_utc' AS mtime_utc"
        if postgres is not None else "mime, size_bytes, mtime_utc"
    )
    # Older folder manifests can mention failed attempts without a saved object.
    eligible = "active" if postgres is not None else "(sha256 IS NOT NULL OR extractor_name IS NOT NULL)"
    statement = f"""
        WITH matches AS (
            SELECT file_id, filename, source_relpath, {columns},
                   substr(source_relpath, length(:prefix) + 1) AS tail
            FROM documents
            WHERE {eligible} AND source_relpath LIKE :pattern ESCAPE '\\'
                  AND substr(source_relpath, 1, length(:prefix)) = :prefix
        ), parts AS (
            SELECT matches.*, {position}(tail, '/') AS separator FROM matches
        ), entries AS (
            SELECT DISTINCT 0 AS kind,
                   CASE WHEN :prefix = '' AND substr(tail, 1, separator - 1) = 'external'
                        THEN 'Other locations' ELSE substr(tail, 1, separator - 1) END AS name,
                   :prefix || substr(tail, 1, separator - 1) AS path,
                   CAST(NULL AS text) AS file_id, CAST(NULL AS text) AS mime,
                   CAST(NULL AS bigint) AS size_bytes, CAST(NULL AS text) AS mtime_utc
            FROM parts WHERE separator > 0
            UNION ALL
            SELECT 1 AS kind, coalesce(nullif(filename, ''), tail) AS name, source_relpath,
                   file_id, mime, size_bytes, mtime_utc
            FROM parts WHERE separator = 0 AND tail <> ''
        )
        SELECT * FROM entries
        WHERE :query = '' OR {position}(lower(name), lower(:query)) > 0
        ORDER BY kind, {SORT_ORDER[sort]}, path, file_id
        LIMIT :limit OFFSET :offset
    """
    values = dict(prefix=prefix, pattern=pattern, query=query.strip(), limit=limit + 1, offset=offset)
    if postgres is not None:
        rows = postgres.query(statement, **values)
    else:
        if not catalog_path(root).is_file():
            ensure_catalog(root)
        try:
            rows = _sidecar_rows(root, statement, values)
        except sqlite3.DatabaseError:
            ensure_catalog(root)
            rows = _sidecar_rows(root, statement, values)
    for row in rows:
        row["kind"] = "file" if row["kind"] else "folder"
    return {"path": path, "items": rows[:limit], "has_more": len(rows) > limit}
