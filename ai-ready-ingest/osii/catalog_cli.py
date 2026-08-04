from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from osii.domain.catalog_db import rebuild_catalog, verify_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the rebuildable OSII catalog.")
    parser.add_argument("command", choices=("rebuild", "verify", "status"))
    parser.add_argument("--root", default=os.getenv("OSII_ROOT", "./osii-data/.osii"))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = rebuild_catalog(root) if args.command == "rebuild" else verify_catalog(root)
    print(json.dumps(result, indent=2))
    return 0 if args.command == "rebuild" or result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
