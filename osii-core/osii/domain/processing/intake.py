import fnmatch
import json
from pathlib import Path

from osii.domain.storage.ids import compute_file_id
from osii.domain.storage.store import object_dir
from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
from osii.indexing.common import embeddings_mapping_path
from osii.domain.read.catalog import load_files_catalog

from .extractor_selection import extractor_chain_for_path, load_extractor_routes
from .pathing import display_rel, path_within, source_relpath as canonical_source_relpath


def is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def parse_patterns(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def match_any(rel_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    rel_posix = rel_path.replace("\\", "/").lower()
    return any(fnmatch.fnmatch(rel_posix, pattern.lower()) for pattern in patterns)


def excluded(rel_path: str, patterns: list[str]) -> bool:
    rel_posix = rel_path.replace("\\", "/").lower()
    return any(fnmatch.fnmatch(rel_posix, pattern.lower()) for pattern in patterns)


def processed_source_relpaths(osii_root: Path) -> set[str]:
    return {
        str(entry.get("source_relpath") or "")
        .strip()
        .replace("\\", "/")
        .strip("/")
        .lower()
        for entry in load_files_catalog(osii_root)
        if entry.get("source_relpath")
    }


def source_relpath(path: Path, data_volume_root: Path) -> str:
    return canonical_source_relpath(path, data_volume_root).strip("/").lower()


def is_source_processed(
    path: Path,
    data_volume_root: Path,
    processed_relpaths: set[str],
) -> bool:
    return source_relpath(path, data_volume_root) in processed_relpaths


def add_processed_counts(
    preview: dict,
    resolved_files: list[Path],
    data_volume_root: Path,
    osii_root: Path,
) -> dict:
    processed_relpaths = processed_source_relpaths(osii_root)
    processed_count = sum(
        1
        for path in resolved_files
        if is_source_processed(path, data_volume_root, processed_relpaths)
    )
    preview["processed_count"] = processed_count
    preview["unprocessed_count"] = len(resolved_files) - processed_count
    return preview


def add_processing_plan(
    preview: dict,
    resolved_files: list[Path],
    osii_root: Path,
    *,
    run_extraction: bool,
    extract_mode: str,
    synthesize: bool,
    embed: bool,
    enrich: bool,
) -> dict:
    """Add a concise, non-mutating operation plan for Intake review."""
    file_ids = [compute_file_id(path) for path in resolved_files]
    unique_file_ids = set(file_ids)
    extracted = {
        file_id
        for file_id in file_ids
        if (object_dir(osii_root, file_id) / "text.txt").is_file()
    }
    stale_by_file = {
        file_id: (get_artifact_staleness(osii_root, file_id) or {}).get("stale", {})
        for file_id in file_ids
    }
    synthesized = {
        file_id
        for file_id in file_ids
        if not stale_by_file[file_id].get("syntheses")
        and (
            (object_dir(osii_root, file_id) / "synth.txt").is_file()
            or any((object_dir(osii_root, file_id) / "syntheses").glob("*.txt"))
        )
    }
    enriched = {
        file_id
        for file_id in file_ids
        if not stale_by_file[file_id].get("enrichments")
        and any((object_dir(osii_root, file_id) / "enrichments").glob("*"))
    }
    embedded: set[str] = set()
    try:
        mapping = embeddings_mapping_path(osii_root)
        if mapping.is_file():
            for line in mapping.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    file_id = json.loads(line).get("file_id")
                    if file_id:
                        if not stale_by_file.get(str(file_id), {}).get("embeddings"):
                            embedded.add(str(file_id))
    except (OSError, ValueError, json.JSONDecodeError):
        embedded = set()

    steps = []
    extraction_count = 0
    if run_extraction:
        extraction_count = len(unique_file_ids) if extract_mode == "reprocess" else len(unique_file_ids - extracted)
        steps.append({
            "id": "extract",
            "label": "Extract text",
            "eligible_count": extraction_count,
            "current_count": len(extracted) if extract_mode == "missing" else 0,
        })
    available_after_extraction = extracted | (unique_file_ids if run_extraction else set())
    if synthesize:
        steps.append({
            "id": "synthesize",
            "label": "Generate synthesis",
            "eligible_count": len(available_after_extraction - synthesized),
            "current_count": len(synthesized),
        })
    if embed:
        steps.append({
            "id": "embed",
            "label": "Build semantic index",
            "eligible_count": len(available_after_extraction - embedded),
            "current_count": len(embedded & unique_file_ids),
            "scope_note": "The semantic index is rebuilt for the current primary corpus.",
        })
    if enrich:
        steps.append({
            "id": "enrich",
            "label": "Run enrichment",
            "eligible_count": len(available_after_extraction - enriched),
            "current_count": len(enriched),
        })
    missing_input = len(unique_file_ids - available_after_extraction)
    preview["processing_plan"] = {
        "matched_count": len(file_ids),
        "unique_document_count": len(unique_file_ids),
        "extracted_count": len(extracted),
        "missing_extraction_count": len(unique_file_ids - extracted),
        "blocked_count": missing_input if any((synthesize, embed, enrich)) else 0,
        "steps": steps,
    }
    return preview


def add_extractor_plan(
    preview: dict,
    resolved_files: list[Path],
    extractor_overrides: dict[str, str] | None = None,
) -> dict:
    routes = load_extractor_routes()
    overrides = {
        str(extension).lower(): str(extractor)
        for extension, extractor in (extractor_overrides or {}).items()
        if extractor
    }
    groups: dict[tuple[str, str], dict] = {}

    for path in resolved_files:
        extension = path.suffix.lower() or "(no extension)"
        chain = (
            [overrides[extension]]
            if extension in overrides
            else extractor_chain_for_path(path, routes)
        )
        extractor = chain[0]
        key = (extension, extractor)
        group = groups.setdefault(
            key,
            {
                "extension": extension,
                "extractor": extractor,
                "fallbacks": chain[1:],
                "count": 0,
                "sample": [],
            },
        )
        group["count"] += 1
        if len(group["sample"]) < 3:
            group["sample"].append(path.name)

    preview["extractor_plan"] = sorted(
        groups.values(),
        key=lambda item: (item["extension"], item["extractor"]),
    )
    return preview


def serialize_queue_items(paths: list[Path], shared_root: Path, upload_root: Path) -> list[dict]:
    items = []
    seen = set()

    for path in paths:
        p = path.resolve()
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "path": str(p),
                "display": display_rel(p, shared_root, upload_root),
                "kind": "folder" if p.is_dir() else "file",
                "source": "shared" if path_within(shared_root, p) else "upload",
            }
        )
    return items


def expand_queue_to_files(
    queue_items: list[dict],
    include_subfolders: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
    show_hidden: bool,
    max_files: int | None,
    max_total_size: int | None,
    shared_root: Path,
    upload_root: Path,
    excluded_paths: list[str] | None = None,
) -> tuple[list[Path], dict]:
    resolved_files: list[Path] = []
    seen = set()
    total_size = 0
    stopped_reason = None
    omitted = {str(Path(path).resolve()) for path in (excluded_paths or [])}
    available_files: list[dict] = []

    for item in queue_items:
        p = Path(item["path"]).resolve()
        if not p.exists():
            continue

        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            iterator = p.rglob("*") if include_subfolders else p.glob("*")
            candidates = sorted((c for c in iterator if c.is_file()), key=lambda c: c.as_posix())
        else:
            continue

        for f in candidates:
            rel_hidden = f.relative_to(p if p.is_dir() else p.parent)

            if not show_hidden and is_hidden(rel_hidden):
                continue

            rel = rel_hidden.as_posix()

            if include_patterns and not match_any(rel, include_patterns):
                continue
            if exclude_patterns and excluded(rel, exclude_patterns):
                continue

            key = str(f.resolve())
            if key in seen:
                continue

            try:
                size = f.stat().st_size
            except Exception:
                continue

            seen.add(key)
            available_files.append({"path": key, "display": display_rel(f, shared_root, upload_root), "size_bytes": size})
            if key in omitted:
                continue

            if max_files is not None and len(resolved_files) >= max_files:
                stopped_reason = f"Stopped after reaching max files limit ({max_files})."
                return resolved_files, {
                    "matched_count": len(resolved_files),
                    "total_size": total_size,
                    "total_size_human": human_size(total_size),
                    "sample": [
                        {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
                        for p in resolved_files[:50]
                    ],
                    "stopped_reason": stopped_reason,
                    "available_files": available_files,
                }

            if max_total_size is not None and total_size + size > max_total_size:
                stopped_reason = f"Stopped after reaching max total size limit ({human_size(max_total_size)})."
                return resolved_files, {
                    "matched_count": len(resolved_files),
                    "total_size": total_size,
                    "total_size_human": human_size(total_size),
                    "sample": [
                        {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
                        for p in resolved_files[:50]
                    ],
                    "stopped_reason": stopped_reason,
                    "available_files": available_files,
                }

            resolved_files.append(f.resolve())
            total_size += size

    preview = {
        "matched_count": len(resolved_files),
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "sample": [
            {"path": str(p), "display": display_rel(p, shared_root, upload_root)}
            for p in resolved_files[:50]
        ],
        "stopped_reason": stopped_reason,
        "available_files": available_files,
    }
    return resolved_files, preview
