"""Headless CLI, using the same Core operations as the dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .models import Filters, ProcessRequest, SelectionRequest, ScanOptions
from .store import VolumeStore, database_path, encode


def add_filters(parser):
    parser.add_argument("--source-id", type=int)
    parser.add_argument("--path", default="", help="Exact path or folder prefix")
    parser.add_argument("--name", default="", help="Filename contains this text")
    parser.add_argument("--suffix", default="")
    parser.add_argument(
        "--text-state", choices=["any", "metadata_only", "extracted"], default="any"
    )
    parser.add_argument("--min-bytes", type=int, default=0)
    parser.add_argument("--max-bytes", type=int)
    parser.add_argument("--modified-after", type=int, help="UTC Unix seconds")
    parser.add_argument("--modified-before", type=int, help="UTC Unix seconds")
    parser.add_argument(
        "--metadata-state", choices=["any", "known", "unavailable"], default="any"
    )
    parser.add_argument(
        "--sidecar-state", choices=["any", "processed", "missing"], default="any"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OSII canonical large-volume inventory and processing"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=database_path(),
        help="Local canonical database, outside source roots",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p = sub.add_parser("migrate")
    p.add_argument("--backup", type=Path, required=True)
    p = sub.add_parser("register")
    p.add_argument("root", type=Path)
    p.add_argument("--name", default="")
    sub.add_parser("sources")
    p = sub.add_parser("scan")
    p.add_argument("source_id", type=int)
    p.add_argument("--readers", type=int, default=2)
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--max-depth", type=int)
    p.add_argument("--show-hidden", action="store_true")
    p.add_argument("--cross-filesystems", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("run_id", type=int)
    sub.add_parser("runs")
    p = sub.add_parser("events")
    p.add_argument("run_id", type=int)
    p.add_argument("--cursor", type=int, default=0)
    p = sub.add_parser("control")
    p.add_argument("run_id", type=int)
    p.add_argument("action", choices=["pause", "resume", "cancel"])
    for command in ("list", "summary", "select", "export"):
        p = sub.add_parser(command)
        add_filters(p)
        if command == "list":
            p.add_argument("--cursor", type=int, default=0)
        if command == "select":
            p.add_argument("--allow-partial", action="store_true")
            p.add_argument("--sample", action="store_true")
            p.add_argument("--seed", default="osii")
            p.add_argument("--per-stratum", type=int, default=2)
            p.add_argument("--max-files", type=int, default=100)
            p.add_argument("--byte-budget", type=int, default=1024**3)
        if command == "export":
            p.add_argument("output", type=Path)
    p = sub.add_parser("process")
    p.add_argument("selection_id", type=int)
    p.add_argument(
        "--stage", choices=["extract", "ocr", "synthesize", "enrich"], default="extract"
    )
    p.add_argument("--endpoint", required=True)
    p.add_argument(
        "--config", default="{}", help="Processor configuration as a JSON object"
    )
    p.add_argument("--max-seconds", type=int, default=3600)
    p.add_argument("--max-file-bytes", type=int, default=50 * 1024**2)
    p = sub.add_parser("report")
    p.add_argument("run_id", type=int)
    p = sub.add_parser("document")
    p.add_argument("entry_id", type=int)
    p.add_argument("--extraction-id", help="Inspect a preserved historical extraction")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--cursor", type=int, default=0)
    p = sub.add_parser("backup")
    p.add_argument("destination", type=Path)
    sub.add_parser("rebuild-search")
    sub.add_parser("work", help="Run the durable worker in the foreground")
    args = parser.parse_args(argv)
    store = VolumeStore(args.db)
    try:
        if args.command == "migrate":
            store.migrate(args.backup)
        store.initialize()
        command = args.command
        result = None
        filters = (
            Filters(**{key: getattr(args, key) for key in Filters.model_fields})
            if command in {"list", "summary", "select", "export"}
            else None
        )
        if command == "register":
            result = store.register_source(args.root, args.name)
        elif command == "sources":
            result = store.sources()
        elif command == "scan":
            result = store.run(
                store.new_scan(
                    args.source_id,
                    ScanOptions(
                        readers=args.readers,
                        include_patterns=args.include,
                        exclude_patterns=args.exclude,
                        max_depth=args.max_depth,
                        show_hidden=args.show_hidden,
                        cross_filesystems=args.cross_filesystems,
                    ),
                )
            )
        elif command == "status":
            result = store.run(args.run_id)
        elif command == "runs":
            result = store.runs()
        elif command == "events":
            result = store.events(args.run_id, args.cursor)
        elif command == "control":
            result = store.control(args.run_id, args.action)
        elif command == "summary":
            result = store.summary(filters)
        elif command == "list":
            result = store.entries(filters, args.cursor)
        elif command == "select":
            result = store.select(
                SelectionRequest(
                    filters=filters,
                    allow_partial=args.allow_partial,
                    sample=args.sample,
                    seed=args.seed,
                    per_stratum=args.per_stratum,
                    max_files=args.max_files,
                    max_bytes=args.byte_budget,
                )
            )
        elif command == "process":
            result = store.run(
                store.new_processing(
                    ProcessRequest(
                        selection_id=args.selection_id,
                        stage=args.stage,
                        endpoint=args.endpoint,
                        config=json.loads(args.config),
                        max_seconds=args.max_seconds,
                        max_file_bytes=args.max_file_bytes,
                    )
                )
            )
        elif command == "document":
            result = (
                store.extraction(args.entry_id, args.extraction_id)
                if args.extraction_id
                else store.document(args.entry_id)
            )
        elif command == "search":
            result = store.search(args.query, args.cursor)
        elif command == "report":
            result = store.report(args.run_id)
        elif command == "backup":
            store.backup(args.destination)
            result = {"backup": str(args.destination)}
        elif command == "rebuild-search":
            store.rebuild_search()
        elif command == "export":
            output = args.output.expanduser().resolve()
            if any(output.is_relative_to(Path(s["root"])) for s in store.sources()):
                raise ValueError("Exports must be outside source roots")
            cursor, count = 0, 0
            with output.open("x", encoding="utf-8") as stream:
                while True:
                    page = store.entries(filters, cursor, 500)
                    for row in page["items"]:
                        stream.write(encode(row) + "\n")
                        count += 1
                    if page["next_cursor"] is None:
                        break
                    cursor = page["next_cursor"]
            result = {"output": str(output), "files": count, "snapshot": False}
        elif command == "work":
            import os
            from .worker import main as work

            os.environ["OSII_VOLUME_DB"] = str(store.path)
            work()
        if result is not None:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.DatabaseError) as exc:
        print(f"OSII volume: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
