import argparse
import json
from pathlib import Path

from osii.search.common import search_segments


def main():
    parser = argparse.ArgumentParser(description="Query the OSII FAISS segment index.")
    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the .osii root",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Query text",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results to return",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Optional query embedding model override",
    )

    args = parser.parse_args()

    osii_root = Path(args.osii_root).resolve()
    results = search_segments(
        osii_root,
        args.query,
        top_k=args.top_k,
        model=args.embedding_model,
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()