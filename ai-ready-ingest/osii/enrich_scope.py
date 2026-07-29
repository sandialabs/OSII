import argparse
import json
from pathlib import Path

from osii.enrichment.registry import resolve_enricher


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


def build_scope(args) -> dict:
    scope_type = (args.scope_type or "").strip().lower()

    if scope_type == "root":
        return {"scope_type": "root"}
    if scope_type == "object":
        return {"scope_type": "object", "file_id": args.file_id}
    if scope_type == "folder":
        return {"scope_type": "folder", "folder_id": args.folder_id}
    if scope_type == "collection":
        return {"scope_type": "collection", "collection_id": args.collection_id}

    raise ValueError(f"Unsupported --scope-type: {args.scope_type}")


def main():
    parser = argparse.ArgumentParser(description="Run one enrichment over one scope.")
    parser.add_argument("--osii-root", required=True, help="Path to the .osii root")
    parser.add_argument("--enricher", required=True, help="Enricher name")
    parser.add_argument("--scope-type", required=True, choices=["root", "object", "folder", "collection"])
    parser.add_argument("--file-id", default=None)
    parser.add_argument("--folder-id", default=None)
    parser.add_argument("--collection-id", default=None)
    parser.add_argument("--option", action="append", default=[])

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    enricher_config = parse_options(args.option)
    scope = build_scope(args)

    enricher = resolve_enricher(args.enricher)
    result = enricher.enrich(
        osii_store=osii_root,
        scope=scope,
        enricher_config=enricher_config,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()