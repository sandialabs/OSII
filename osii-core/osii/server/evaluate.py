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
from osii.server.model_connections import ModelConnections, ConfiguredModelProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries")
    parser.add_argument("--mode", choices=["lexical", "semantic", "hybrid"], default="lexical")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--allow-paid-embeddings", action="store_true")
    parser.add_argument("--profiles", nargs="+", help="Evaluate advanced RAG profile IDs instead of retrieval alone")
    parser.add_argument("--username", help="Existing active administrator for scoped advanced RAG evaluation")
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--output", help="Write the JSON evaluation report to this path")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 50:
        parser.error("--top-k must be between 1 and 50")
    if not args.profiles and args.mode != "lexical" and not args.allow_paid_embeddings:
        parser.error("Semantic/hybrid evaluation requires explicit --allow-paid-embeddings")
    settings = Settings.environment()
    store = PostgresStore(settings.database_url)
    store.ready()
    if args.profiles:
        from osii.server.rag import RagSession
        from osii.rag.strategies.evaluation import evaluate_response
        if not args.allow_model_calls or not args.username:
            parser.error("Advanced RAG evaluation needs --username and --allow-model-calls (chat, embeddings, and configured reranking)")
        account = store.account(username=args.username)
        if not account or not account["active"] or account["role"] != "admin":
            parser.error("Choose an existing active administrator")
        if len(args.profiles) > 3 or len(set(args.profiles)) != len(args.profiles):
            parser.error("Choose one to three distinct profiles")
        connections = ModelConnections(store, settings)
        provider = ConfiguredModelProvider(connections)
        report = []
        with open(args.queries, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip(): continue
                case = json.loads(line)
                session = RagSession(store, provider, connections, account, case["query"], case.get("scope", {"scope_type": "root"}), [])
                session.validate(args.profiles)
                runs = [{"profile_id": profile, "corpus_revision": session.revision,
                         **evaluate_response(session.run(profile), case)} for profile in args.profiles]
                session.guard()
                report.extend(runs)
        value = {"evaluation": "supporting-source coverage and literal answer checks; not semantic judging", "results": report}
        content = json.dumps(value, indent=2)
        if args.output:
            from pathlib import Path
            Path(args.output).write_text(content + "\n", encoding="utf-8")
        print(content)
        return
    library = Library(store, ConfiguredModelProvider(ModelConnections(store, settings)))
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
