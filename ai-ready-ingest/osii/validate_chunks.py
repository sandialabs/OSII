import argparse
import json
from pathlib import Path

from osii.domain.storage.store import embeddings_chunks_manifest_path


def main():
    parser = argparse.ArgumentParser(description="Validate the chunk manifest JSONL file.")
    parser.add_argument("--osii-root", required=True, help="Path to .osii root")
    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    path = embeddings_chunks_manifest_path(osii_root)

    if not path.exists():
        raise RuntimeError(f"Chunk manifest not found: {path}")

    good = 0
    bad = 0

    for line_num, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue

        try:
            json.loads(raw)
            good += 1
        except Exception as exc:
            bad += 1
            print(f"BAD line {line_num}: {exc}")
            print(raw[:500])
            print("")

    print(f"Valid rows: {good}")
    print(f"Invalid rows: {bad}")


if __name__ == "__main__":
    main()