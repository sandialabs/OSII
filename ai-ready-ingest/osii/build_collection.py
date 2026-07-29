import argparse
from datetime import datetime, UTC
from pathlib import Path

import tomli_w

from osii.domain.processing.intake import expand_queue_to_files
from osii.domain.storage.root_descriptor import write_root_toml
from osii.domain.storage.folders import folder_stats, get_or_create_folder_id
from osii.domain.processing.folder_rebuild import build_folder_artifacts

from osii.domain.storage.ids import compute_file_id
from osii.domain.storage.store import ensure_osii_store_layout, run_metadata_path, root_synth_path
from osii.domain.processing.synth_routing import (
    load_object_synth_routes,
    load_folder_synth_routes,
    choose_object_synthesizer,
    choose_folder_synthesizer,
)
from osii.extraction.dispatcher import dispatch_extract
from osii.domain.read.folder_synthesis import get_folder_synthesis_text
from osii.synthesis.folder_registry import resolve_folder_synthesizer
from osii.synthesis.registry import resolve_synthesizer


def parse_patterns(values: list[str] | None) -> list[str]:
    return [v.strip() for v in (values or []) if v.strip()]


def load_parser_routes(config_path: Path) -> list[dict]:
    import tomllib

    if not config_path.exists():
        return [{"name": "default-tika", "extractor": "tika", "extensions": ["*"]}]

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("routes", [])


def choose_parser(path: Path, routes: list[dict]) -> str:
    suffix = path.suffix.lower()
    for route in routes:
        exts = route.get("extensions", [])
        if "*" in exts or suffix in [e.lower() for e in exts]:
            return route["extractor"]
    return "tika"


def relpath_under(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        return "" if rel == "." else rel
    except Exception:
        return path.name


def write_run_metadata(
    *,
    osii_store: Path,
    run_name: str,
    data_root: Path,
    resolved_files: list[Path],
    extractor_override: str | None,
    object_synthesizer_name: str | None,
    folder_synthesizer_name: str | None,
    context: str,
    stats: dict,
) -> Path:
    path = run_metadata_path(osii_store, run_name)

    payload = {
        "run": {
            "name": run_name,
            "generated_utc": datetime.now(UTC).isoformat(),
            "data_root": str(data_root),
            "resolved_file_count": len(resolved_files),
            "context": context or "",
        },
        "config": {
            "extractor_override": extractor_override or "",
            "object_synthesizer": object_synthesizer_name or "",
            "folder_synthesizer": folder_synthesizer_name or "",
        },
        "stats": stats,
    }

    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Build a full OSII collection from a data root.")
    parser.add_argument("--data-root", required=True, help="Path to the source data root")
    parser.add_argument("--osii-root", required=True, help="Path to the .osii root")
    parser.add_argument("--include-pattern", action="append", default=[], help="Include glob pattern (repeatable)")
    parser.add_argument("--exclude-pattern", action="append", default=[], help="Exclude glob pattern (repeatable)")
    parser.add_argument("--max-files", type=int, default=None, help="Optional max files limit")
    parser.add_argument("--extractor", default=None, help="Optional extractor override for all files")
    parser.add_argument("--synthesizer", default=None, help="Optional object-level synthesizer override")
    parser.add_argument("--folder-synthesizer", default=None, help="Optional folder-level synthesizer override")
    parser.add_argument("--context", default="", help="Optional context/expert guidance")
    parser.add_argument("--run-name", default="", help="Optional run name")

    args = parser.parse_args()

    data_root = Path(args.data_root).resolve()
    osii_root = Path(args.osii_root).resolve()
    ensure_osii_store_layout(osii_root)

    if not data_root.exists() or not data_root.is_dir():
        raise RuntimeError(f"Data root does not exist or is not a directory: {data_root}")

    queue_items = [
        {
            "path": str(data_root),
            "display": str(data_root),
            "kind": "folder",
            "source": "shared",
        }
    ]

    resolved_files, preview = expand_queue_to_files(
        queue_items=queue_items,
        include_subfolders=True,
        include_patterns=parse_patterns(args.include_pattern),
        exclude_patterns=parse_patterns(args.exclude_pattern),
        show_hidden=False,
        max_files=args.max_files,
        max_total_size=None,
        shared_root=data_root,
        upload_root=data_root,
    )

    parser_routes_path = Path("config/parser_routes.toml").resolve()
    parser_routes = load_parser_routes(parser_routes_path)

    object_synth_routes = load_object_synth_routes()
    folder_synth_routes = load_folder_synth_routes()

    run_name = args.run_name or f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    root_folder_id = get_or_create_folder_id(osii_root, "")

    write_root_toml(
        osii_store=osii_root,
        root_folder_id=root_folder_id,
        host_path=str(data_root),
        container_path=str(data_root),
        notes=args.context or "",
        tool_versions={
            "pipeline_version": "osii-v1-draft",
        },
    )

    object_synthesizer_override = args.synthesizer or None
    folder_synthesizer_override = args.folder_synthesizer or None

    print(f"Resolved {len(resolved_files)} file(s).")
    success = 0
    partial = 0
    failed = 0
    synthesized_objects = 0
    synthesized_folders = 0
    synthesized_root = 0

    for i, src in enumerate(resolved_files, start=1):
        extractor_name = args.extractor or choose_parser(src, parser_routes)
        print(f"[{i}/{len(resolved_files)}] Extracting {src.name} with {extractor_name}")

        try:
            extract_result = dispatch_extract(
                extractor_name=extractor_name,
                source_path=src,
                data_volume_root=data_root,
                osii_store=osii_root,
                expert_context=args.context or None,
                extractor_config={},
            )

            file_id = extract_result["file_id"]
            extract_error = extract_result.get("error")

            synth_error = None
            synth_name = object_synthesizer_override or choose_object_synthesizer(src, object_synth_routes)

            if synth_name:
                print(f"    Synthesizing object with {synth_name}")
                try:
                    synthesizer = resolve_synthesizer(synth_name)
                    synthesizer.synthesize(
                        osii_store=osii_root,
                        file_id=file_id,
                        expert_context=args.context or None,
                        synthesizer_config={},
                    )
                    synthesized_objects += 1
                except Exception as exc:
                    synth_error = str(exc)

            if extract_error or synth_error:
                partial += 1
                print(f"    PARTIAL: extract_error={extract_error!r} synth_error={synth_error!r}")
            else:
                success += 1
                print("    DONE")

        except Exception as exc:
            failed += 1
            print(f"    ERROR: {exc}")

    top_level_doc_count, top_level_subfolder_count, folder_id_map, all_folders = build_folder_artifacts(
        resolved_files=resolved_files,
        data_volume_root=data_root,
        shared_root=data_root,
        osii_store=osii_root,
        root_folder_id=root_folder_id,
    )

    # Folder-level synthesis: deepest folders first
    folders_by_depth = sorted(all_folders, key=lambda p: len(p.resolve().parts), reverse=True)

    for folder in folders_by_depth:
        folder_id = folder_id_map[str(folder)]
        folder_relpath = relpath_under(data_root, folder)
        synth_name = folder_synthesizer_override or choose_folder_synthesizer(folder_relpath, folder_synth_routes)

        if not synth_name:
            continue

        print(f"Synthesizing folder {folder_relpath or data_root.name} with {synth_name}")
        try:
            synthesizer = resolve_folder_synthesizer(synth_name)
            synthesizer.synthesize_folder(
                osii_store=osii_root,
                folder_id=folder_id,
                expert_context=args.context or None,
                synthesizer_config={},
            )
            synthesized_folders += 1
        except Exception as exc:
            print(f"    FOLDER SYNTH ERROR: {exc}")

    # Root synthesis: copy root folder synthesis into root.synth.txt if present
    root_text = get_folder_synthesis_text(osii_root, root_folder_id)
    if root_text:
        root_synth_path(osii_root).write_text(root_text, encoding="utf-8")
        synthesized_root = 1

    run_meta = write_run_metadata(
        osii_store=osii_root,
        run_name=run_name,
        data_root=data_root,
        resolved_files=resolved_files,
        extractor_override=args.extractor,
        object_synthesizer_name=object_synthesizer_override or "(routed per file)",
        folder_synthesizer_name=folder_synthesizer_override or "(routed per folder)",
        context=args.context,
        stats={
            "success": success,
            "partial": partial,
            "failed": failed,
            "synthesized_objects": synthesized_objects,
            "synthesized_folders": synthesized_folders,
            "synthesized_root": synthesized_root,
        },
    )

    print("")
    print("Build complete.")
    print(f"  success              : {success}")
    print(f"  partial              : {partial}")
    print(f"  failed               : {failed}")
    print(f"  synthesized objects  : {synthesized_objects}")
    print(f"  synthesized folders  : {synthesized_folders}")
    print(f"  synthesized root     : {synthesized_root}")
    print(f"  run metadata         : {run_meta}")
    print(f"  osii                 : {osii_root}")


if __name__ == "__main__":
    main()
