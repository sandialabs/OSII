import fnmatch
import json
import os
import stat
from pathlib import Path

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


def _catalog_key(path: Path, data_volume_root: Path) -> str:
    """Catalog key for a path that has already been resolved by discovery."""
    try:
        relative = path.relative_to(data_volume_root).as_posix()
    except ValueError:
        relative = "external/" + path.as_posix().replace(":", "").lstrip("/")
    return relative.strip("/").lower()


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
        if _catalog_key(path, data_volume_root) in processed_relpaths
    )
    preview["processed_count"] = processed_count
    preview["unprocessed_count"] = len(resolved_files) - processed_count
    return preview


def add_processing_plan(
    preview: dict,
    resolved_files: list[Path],
    osii_root: Path,
    *,
    data_volume_root: Path,
    run_extraction: bool,
    extract_mode: str,
    synthesize: bool,
    embed: bool,
    enrich: bool,
) -> dict:
    """Estimate work from saved identities; preview never reads source bytes."""
    catalog = {str(row["source_relpath"]).replace("\\", "/").strip("/").lower(): row["file_id"]
               for row in load_files_catalog(osii_root) if row.get("file_id")}
    file_ids = []
    known_file_ids = set()
    # expand_queue_to_files has already resolved paths. Do not resolve every
    # component again over the network just to look up saved metadata.
    for path in resolved_files:
        file_id = catalog.get(_catalog_key(path, data_volume_root))
        if file_id:
            known_file_ids.add(file_id)
        file_ids.append(file_id or f"unverified:{path}")
    unique_file_ids = set(file_ids)
    extracted = {
        file_id
        for file_id in known_file_ids
        if (object_dir(osii_root, file_id) / "text.txt").is_file()
    }
    stale_by_file = {
        file_id: (get_artifact_staleness(osii_root, file_id) or {}).get("stale", {})
        for file_id in known_file_ids
    }
    synthesized = {
        file_id
        for file_id in known_file_ids
        if not stale_by_file[file_id].get("syntheses")
        and (
            (object_dir(osii_root, file_id) / "synth.txt").is_file()
            or any((object_dir(osii_root, file_id) / "syntheses").glob("*.txt"))
        )
    }
    enriched = {
        file_id
        for file_id in known_file_ids
        if not stale_by_file[file_id].get("enrichments")
        and any((object_dir(osii_root, file_id) / "enrichments").glob("*"))
    }
    embedded: set[str] = set()
    try:
        mapping = embeddings_mapping_path(osii_root)
        if embed and known_file_ids and mapping.is_file():
            with mapping.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        file_id = str(json.loads(line).get("file_id") or "")
                        if file_id in known_file_ids and not stale_by_file.get(file_id, {}).get("embeddings"):
                            embedded.add(file_id)
                        if embedded == known_file_ids:
                            break
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
        "estimated": True,
        "note": "Metadata estimate. Content identity, deduplication, and current artifacts are verified when processing starts.",
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


def _metadata_files(root: Path, recursive: bool, show_hidden: bool):
    """Reuse DirEntry metadata instead of repeatedly resolving/statting paths."""
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if not show_hidden and entry.name.startswith("."):
                    continue
                path = directory / entry.name
                if entry.is_symlink():
                    # Keep the existing explicit file-link behavior. Mounted
                    # mode still revalidates the resolved target at the API.
                    if path.is_file():
                        yield path, path.stat(), True
                elif entry.is_dir(follow_symlinks=False):
                    if recursive:
                        pending.append(path)
                else:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISREG(info.st_mode):
                        yield path, info, False


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
    shared_root = shared_root.resolve()
    upload_root = upload_root.resolve()

    def label(path: Path) -> str:
        # These paths are already canonical; avoid repeated network realpath
        # calls for every label and every root comparison.
        if path.is_relative_to(shared_root):
            return f"{shared_root.name}/{path.relative_to(shared_root).as_posix()}"
        if path.is_relative_to(upload_root):
            return f"Uploads/{path.relative_to(upload_root).as_posix()}"
        return path.as_posix()

    for item in queue_items:
        p = Path(item["path"]).resolve()
        if not p.exists():
            continue

        directory = p.is_dir()
        if directory:
            candidates = sorted(_metadata_files(p, include_subfolders, show_hidden), key=lambda item: item[0].as_posix())
        elif p.is_file():
            candidates = [(p, p.stat(), False)]
        else:
            continue

        for f, info, is_link in candidates:
            rel_hidden = f.relative_to(p if directory else p.parent)

            if not show_hidden and is_hidden(rel_hidden):
                continue

            rel = rel_hidden.as_posix()

            if include_patterns and not match_any(rel, include_patterns):
                continue
            if exclude_patterns and excluded(rel, exclude_patterns):
                continue

            key = str(f.resolve() if is_link else f)
            if key in seen:
                continue

            size = info.st_size

            seen.add(key)
            available_files.append({"path": key, "display": label(Path(key)), "size_bytes": size})
            if key in omitted:
                continue

            if max_files is not None and len(resolved_files) >= max_files:
                stopped_reason = f"Stopped after reaching max files limit ({max_files})."
                return resolved_files, {
                    "matched_count": len(resolved_files),
                    "total_size": total_size,
                    "total_size_human": human_size(total_size),
                    "sample": [
                        {"path": str(p), "display": label(p)}
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
                        {"path": str(p), "display": label(p)}
                        for p in resolved_files[:50]
                    ],
                    "stopped_reason": stopped_reason,
                    "available_files": available_files,
                }

            resolved_files.append(Path(key))
            total_size += size

    preview = {
        "matched_count": len(resolved_files),
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "sample": [
            {"path": str(p), "display": label(p)}
            for p in resolved_files[:50]
        ],
        "stopped_reason": stopped_reason,
        "available_files": available_files,
    }
    return resolved_files, preview
