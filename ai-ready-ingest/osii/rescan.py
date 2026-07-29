import argparse
import json
from pathlib import Path

from osii.domain.processing.reconcile import reconcile_osii_with_source
from osii.domain.processing.reconcile_apply import apply_reconciliation


def parse_patterns(values: list[str] | None) -> list[str]:
    return [v.strip() for v in (values or []) if v.strip()]


def main():
    parser = argparse.ArgumentParser(description="Scan source files and reconcile them with the current OSII store.")
    parser.add_argument("--data-root", required=True, help="Path to source data root")
    parser.add_argument("--osii-root", required=True, help="Path to .osii root")
    parser.add_argument("--include-pattern", action="append", default=[], help="Include glob pattern (repeatable)")
    parser.add_argument("--exclude-pattern", action="append", default=[], help="Exclude glob pattern (repeatable)")
    parser.add_argument("--show-hidden", action="store_true", help="Include hidden files")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--apply", action="store_true", help="Apply safe reconciliation updates")
    parser.add_argument(
        "--extractor",
        default=None,
        help="Optional extractor override used to re-extract changed and new files during apply mode",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Optional expert context used if re-extraction occurs",
    )
    parser.add_argument(
        "--no-rebuild-folders",
        action="store_true",
        help="Skip rebuilding folder manifests/tree during apply mode",
    )

    args = parser.parse_args()

    data_root = Path(args.data_root).resolve()
    osii_root = Path(args.osii_root).resolve()

    result = reconcile_osii_with_source(
        osii_root=osii_root,
        data_root=data_root,
        include_patterns=parse_patterns(args.include_pattern),
        exclude_patterns=parse_patterns(args.exclude_pattern),
        show_hidden=args.show_hidden,
    )

    if args.apply:
        applied = apply_reconciliation(
            reconcile_result=result,
            osii_root=osii_root,
            data_root=data_root,
            extractor_name=args.extractor,
            expert_context=args.context,
            rebuild_folders=not args.no_rebuild_folders,
        )
        result["applied"] = applied

    if args.json:
        print(json.dumps(result, indent=2))
        return

    summary = result["summary"]
    print("Rescan summary")
    print(f"  unchanged      : {summary['unchanged']}")
    print(f"  changed        : {summary['changed']}")
    print(f"  moved          : {summary['moved']}")
    print(f"  missing_source : {summary['missing_source']}")
    print(f"  new_files      : {summary['new_files']}")

    for section in ("changed", "moved", "missing_source", "new_files"):
        items = result.get(section, [])
        if not items:
            continue
        print("")
        print(section)
        for item in items:
            print(f"  - {item}")

    if args.apply:
        print("")
        print("apply results")
        for key, value in result["applied"].items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()