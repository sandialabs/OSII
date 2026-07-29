import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_collections_dir(osii_root: Path) -> Path:
    path = (osii_root / ".collections").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_collections_db_path(osii_root: Path) -> Path:
    return get_collections_dir(osii_root) / "collections.sqlite"


def connect_db(osii_root: Path) -> sqlite3.Connection:
    path = get_collections_db_path(osii_root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_collections_db(osii_root: Path) -> Path:
    path = get_collections_db_path(osii_root)
    with connect_db(osii_root) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                kind TEXT NOT NULL DEFAULT 'manual',
                color TEXT,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_documents (
                collection_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                PRIMARY KEY (collection_id, file_id),
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    return path


def _ensure_kind_column(osii_root: Path) -> None:
    with connect_db(osii_root) as conn:
        cols = conn.execute("PRAGMA table_info(collections)").fetchall()
        names = {row["name"] for row in cols}
        if "kind" not in names:
            conn.execute("ALTER TABLE collections ADD COLUMN kind TEXT NOT NULL DEFAULT 'manual'")
            conn.commit()


def _row_to_collection(row: sqlite3.Row, document_count: int | None = None) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "kind": row["kind"] if "kind" in row.keys() else "manual",
        "color": row["color"],
        "document_count": document_count if document_count is not None else 0,
        "created_utc": row["created_utc"],
        "updated_utc": row["updated_utc"],
    }


def _collection_document_count(conn: sqlite3.Connection, collection_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM collection_documents WHERE collection_id = ?",
        (collection_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def list_collections(osii_root: Path) -> list[dict]:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        rows = conn.execute(
            "SELECT * FROM collections ORDER BY lower(name)"
        ).fetchall()

        out = []
        for row in rows:
            out.append(_row_to_collection(row, _collection_document_count(conn, row["id"])))
        return out


def create_collection(
    osii_root: Path,
    *,
    name: str,
    description: str | None = None,
    kind: str = "manual",
    color: str | None = None,
) -> dict:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    name = (name or "").strip()
    kind = (kind or "manual").strip() or "manual"

    if not name:
        raise ValueError("Collection name is required.")

    collection_id = f"col-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()

    with connect_db(osii_root) as conn:
        conn.execute(
            """
            INSERT INTO collections (id, name, description, kind, color, created_utc, updated_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (collection_id, name, description, kind, color, now, now),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM collections WHERE id = ?",
            (collection_id,),
        ).fetchone()
        return _row_to_collection(row, 0)


def get_collection(osii_root: Path, collection_id: str) -> dict | None:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        row = conn.execute(
            "SELECT * FROM collections WHERE id = ?",
            (collection_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_collection(row, _collection_document_count(conn, collection_id))


def update_collection(
    osii_root: Path,
    collection_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    kind: str | None = None,
    color: str | None = None,
) -> dict | None:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    updates = []
    values = []

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Collection name may not be empty.")
        updates.append("name = ?")
        values.append(name)

    if description is not None:
        updates.append("description = ?")
        values.append(description)

    if kind is not None:
        kind = kind.strip() or "manual"
        updates.append("kind = ?")
        values.append(kind)

    if color is not None:
        updates.append("color = ?")
        values.append(color)

    if not updates:
        return get_collection(osii_root, collection_id)

    updates.append("updated_utc = ?")
    values.append(utc_now_iso())
    values.append(collection_id)

    with connect_db(osii_root) as conn:
        cur = conn.execute(
            f"UPDATE collections SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None

    return get_collection(osii_root, collection_id)


def delete_collection(osii_root: Path, collection_id: str) -> bool:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        cur = conn.execute(
            "DELETE FROM collections WHERE id = ?",
            (collection_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def list_collection_documents(osii_root: Path, collection_id: str) -> list[str]:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        rows = conn.execute(
            """
            SELECT file_id
            FROM collection_documents
            WHERE collection_id = ?
            ORDER BY created_utc, file_id
            """,
            (collection_id,),
        ).fetchall()
        return [row["file_id"] for row in rows]


def add_documents_to_collection(osii_root: Path, collection_id: str, file_ids: list[str]) -> dict:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    now = utc_now_iso()

    added = []
    already_present = []

    with connect_db(osii_root) as conn:
        existing = {
            row["file_id"]
            for row in conn.execute(
                "SELECT file_id FROM collection_documents WHERE collection_id = ?",
                (collection_id,),
            ).fetchall()
        }

        for file_id in file_ids:
            if file_id in existing:
                already_present.append(file_id)
                continue

            conn.execute(
                """
                INSERT INTO collection_documents (collection_id, file_id, created_utc)
                VALUES (?, ?, ?)
                """,
                (collection_id, file_id, now),
            )
            added.append(file_id)

        conn.commit()

    return {
        "collection_id": collection_id,
        "added": added,
        "already_present": already_present,
    }


def remove_document_from_collection(osii_root: Path, collection_id: str, file_id: str) -> dict:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        cur = conn.execute(
            """
            DELETE FROM collection_documents
            WHERE collection_id = ? AND file_id = ?
            """,
            (collection_id, file_id),
        )
        conn.commit()

    return {
        "collection_id": collection_id,
        "file_id": file_id,
        "removed": cur.rowcount > 0,
    }


def list_collections_for_file(osii_root: Path, file_id: str) -> list[dict]:
    init_collections_db(osii_root)
    _ensure_kind_column(osii_root)

    with connect_db(osii_root) as conn:
        rows = conn.execute(
            """
            SELECT c.*
            FROM collections c
            INNER JOIN collection_documents cd
              ON c.id = cd.collection_id
            WHERE cd.file_id = ?
            ORDER BY lower(c.name)
            """,
            (file_id,),
        ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "kind": row["kind"] if "kind" in row.keys() else "manual",
            }
            for row in rows
        ]