"""Evaluate labelled real queries without changing corpus data or configuration.

JSONL input: {"query": "...", "expected_sources": ["relative/path.pdf"]}
Run with --mode hybrid --allow-paid-embeddings to enable query embedding calls.
"""
import argparse
import json

from osii.domain.library import Library
from osii.persistence.postgres import PostgresStore
from osii.server.config import Settings
from osii.model_provider import ModelProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries")
    parser.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="lexical")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--allow-paid-embeddings", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 50:
        parser.error("--top-k must be between 1 and 50")
    if args.mode != "lexical" and not args.allow_paid_embeddings:
        parser.error("Semantic/hybrid evaluation requires explicit --allow-paid-embeddings")
    settings = Settings.environment()
    store = PostgresStore(settings.database_url)
    store.ready()
    library = Library(store, settings.provider())
    recall, reciprocal, count = 0., 0., 0
    with open(args.queries, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            case = json.loads(line)
            expected = set(case["expected_sources"])
            if not expected:
                raise ValueError("Every labelled query needs at least one expected source")
            result = library.search(case["query"], args.mode, args.top_k, {"scope_type": "root"})
            ordered = list(dict.fromkeys(row["source_relpath"] for row in result["results"]))
            recall += len(expected & set(ordered)) / len(expected)
            reciprocal += next((1 / rank for rank, name in enumerate(ordered, 1) if name in expected), 0)
            count += 1
    if not count:
        raise ValueError("No labelled queries were provided")
    print(json.dumps({"queries": count, "mode": args.mode, "top_k": args.top_k,
        "source_recall": recall / count, "mean_reciprocal_rank": reciprocal / count}, indent=2))


if __name__ == "__main__":
    main()
