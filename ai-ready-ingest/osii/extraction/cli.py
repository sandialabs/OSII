import argparse
import json
import sys
from pathlib import Path

from osii.extraction.dispatcher import dispatch_extract


def parse_options(option_list: list[str]) -> dict:
    result = {}
    for item in option_list:
        if "=" not in item:
            raise ValueError(f"Invalid --option value '{item}', expected key=value")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid --option value '{item}', empty key")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a single OSII extractor on one file."
    )
    parser.add_argument(
        "--source-file",
        help="Path to the source file to extract",
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="Data root used to compute source_relpath",
    )
    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the .osii root where outputs will be written",
    )
    parser.add_argument(
        "--extractor",
        required=True,
        help="Extractor name, e.g. 'pdf_default', 'tika_catchall', or 'osii_tesseract'",
    )
    parser.add_argument(
        "--expert-context",
        default=None,
        help="Optional free-text expert guidance",
    )
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        help="Extractor-specific option in key=value form. Repeatable.",
    )

    args = parser.parse_args()

    source_file = Path(args.source_file).resolve()
    data_root = Path(args.data_root).resolve()
    osii_root = Path(args.osii_root).resolve()

    if not source_file.exists() or not source_file.is_file():
        print(f"ERROR: source file not found: {source_file}", file=sys.stderr)
        return 2

    if not data_root.exists():
        print(f"ERROR: data root does not exist: {data_root}", file=sys.stderr)
        return 2

    osii_root.mkdir(parents=True, exist_ok=True)

    try:
        extractor_config = parse_options(args.option)
    except Exception as exc:
        print(f"ERROR: could not parse extractor options: {exc}", file=sys.stderr)
        return 2

    try:
        result = dispatch_extract(
            extractor_name=args.extractor,
            source_path=source_file,
            data_volume_root=data_root,
            osii_store=osii_root,
            expert_context=args.expert_context,
            extractor_config=extractor_config,
        )
    except Exception as exc:
        print(f"ERROR: extraction failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
