"""Bounded handoff from canonical discovery evidence to ordinary sidecar Intake."""

from __future__ import annotations

from pathlib import Path
import stat

from .scanner import checked_path
from .store import VolumeStore, database_path


def selection_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("inventory_selection_id must be a positive integer")
    return value


def staged_bundle(osii_root: Path, selection_id: int, *, store: VolumeStore | None = None) -> dict:
    store = store or VolumeStore(database_path(osii_root))
    members = store.staged_members(selection_id)
    return {
        "database": str(store.path),
        "selection_id": selection_id,
        "coverage": store.selection(selection_id)["coverage"],
        "members": members,
    }


def member_path(member: dict) -> Path:
    # Lexical composition only. Source identity and filesystem access are checked
    # in the worker, never while reviewing or enqueueing a frozen selection.
    relative = Path(member["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid frozen source path")
    return Path(member["root"]) / relative


def validate_member(bundle: dict, member: dict) -> None:
    store = VolumeStore(Path(bundle["database"]))
    source = store.source(member["source_id"])
    if source["generation"] != member["source_generation"]:
        raise ValueError("Source registration changed; discover and stage again")
    with store.connect() as conn:
        entry = conn.execute(
            "SELECT revision,status,metadata_state FROM entries WHERE id=?",
            (member["entry_id"],),
        ).fetchone()
    if (
        entry is None
        or entry["revision"] != member["revision"]
        or entry["status"] != "present"
        or entry["metadata_state"] != "known"
    ):
        raise ValueError("Inventory revision changed; discover and stage again")
    root = Path(source["root"])
    root_info = root.stat()
    if (str(root_info.st_dev), str(root_info.st_ino)) != (
        member["device"],
        member["inode"],
    ):
        raise ValueError("Source root identity changed; reconnect the original share")
    path = checked_path(root, member["path"])
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Staged path is no longer a regular file")
    if (str(info.st_dev), str(info.st_ino)) != (
        member["file_device"],
        member["file_inode"],
    ):
        raise ValueError("Staged file identity changed; discover and stage again")
    if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
        member["size_bytes"],
        member["mtime_ns"],
        member["ctime_ns"],
    ):
        raise ValueError("File changed since discovery; discover and stage again")
    if info.st_size > 50 * 1024 * 1024:
        raise ValueError(
            "File exceeds the 50 MiB Intake staging limit; select a smaller file"
        )


def selection_preview(
    bundle: dict, overrides: dict | None = None, operations: dict | None = None
) -> dict:
    from osii.domain.processing.intake import add_extractor_plan, human_size

    files = [member_path(member) for member in bundle["members"]]
    total = sum(member["size_bytes"] for member in bundle["members"])
    available = [
        {
            "path": str(member_path(m)),
            "display": m["path"],
            "size": m["size_bytes"],
            "size_bytes": m["size_bytes"],
            "size_human": human_size(m["size_bytes"]),
        }
        for m in bundle["members"][:100]
    ]
    preview = {
        "matched_count": len(files),
        "total_size": total,
        "total_size_human": human_size(total),
        "available_files": available,
        "processed_count": 0,
        "unprocessed_count": len(files),
        "truncated": len(files) > 100,
        "skipped_count": 0,
        "sample": available[:10],
    }
    operations = operations or {}
    processed = sum(
        bool(member.get("sidecar_processed")) for member in bundle["members"]
    )
    preview.update(processed_count=processed, unprocessed_count=len(files) - processed)
    steps = [
        ("extract", "Read text", operations.get("run_extraction", True)),
        ("synthesize", "Summaries", operations.get("synthesizer_name")),
        ("embed", "Embed selected documents", operations.get("build_embeddings")),
        ("enrich", "Enrichment", operations.get("enricher_name")),
    ]
    preview["processing_plan"] = {
        "estimated": True,
        "matched_count": len(files),
        "unique_document_count": len(files),
        "extracted_count": processed,
        "missing_extraction_count": len(files) - processed,
        "blocked_count": 0,
        "note": "Frozen membership. Content identity, reuse, and read permission are checked in the worker; duplicate content may share an object. Embeddings process only these documents and preserve other library vectors.",
        "steps": [
            {
                "id": step,
                "label": label,
                "eligible_count": len(files),
                "current_count": 0,
            }
            for step, label, enabled in steps
            if enabled
        ],
    }
    add_extractor_plan(preview, files, overrides or {})
    return {
        "preview": preview,
        "resolved_files": available,
        "inventory_selection_id": bundle["selection_id"],
        "queue_items": [],
    }
