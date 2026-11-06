"""Run a synthetic offline demonstration or an explicit read-only Core experiment."""
import argparse
from dataclasses import asdict
import getpass
import json
import os
from pathlib import Path

from .contracts import Context, Decision, Evidence, Limits, Question, Scope, StrategyError


def demo(strategy: str):
    from .haystack import run
    first = Evidence("overview:0", "overview", "The calibration report identifies a source in a separate isotope table.", "overview.txt", corpus_revision="synthetic-1")
    second = Evidence("isotopes:0", "isotopes", "The detector calibration source is americium-241 (241Am).", "isotopes.txt", corpus_revision="synthetic-1")

    def retrieve(query, *, top_k):
        return [second] if "isotope table" in query.casefold() else [first]

    def decide(context: Context):
        if second in context.evidence:
            return Decision("answer", answer=second.text, citation_ids=(second.id,), model="synthetic-decider")
        return Decision("retrieve", query="detector calibration isotope table", model="synthetic-decider") if context.can_retrieve else Decision("abstain", model="synthetic-decider")

    return run(Question("Which isotope calibrates the detector?"), retrieve=retrieve, decide=decide, strategy=strategy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--demo", action="store_true", help="Synthetic data and deterministic decisions; no network or model")
    parser.add_argument("--strategy", choices=["single-pass", "iterative"], default="iterative")
    parser.add_argument("--api-url", help="Core root URL, e.g. https://osii.app")
    parser.add_argument("--username", help="Hosted Core username; password is prompted invisibly")
    parser.add_argument("--scope", choices=["root", "folder", "collection", "object"], default="root")
    parser.add_argument("--scope-id", default="")
    parser.add_argument("--mode", choices=["lexical", "hybrid", "semantic"], default="lexical")
    parser.add_argument("--chat-url", help="Compatible API base URL, including /v1 where applicable")
    parser.add_argument("--chat-model", help="Exact model ID; never inferred or silently substituted")
    parser.add_argument("--allow-model-calls", action="store_true", help="Explicitly enable external model calls, which may incur charges")
    parser.add_argument("--max-retrievals", type=int, default=3)
    parser.add_argument("--max-model-calls", type=int, default=3)
    args = parser.parse_args()
    if args.demo:
        if any((args.question, args.api_url, args.username, args.chat_url, args.chat_model, args.allow_model_calls)):
            parser.error("--demo is isolated; omit endpoint, credential, question, and model options")
        result = demo(args.strategy)
        print(json.dumps({"synthetic_demo": True, **asdict(result)}, indent=2))
        return
    if not all((args.question, args.api_url, args.chat_url, args.chat_model, args.allow_model_calls)):
        parser.error("Live experiments require a question, --api-url, --chat-url, --chat-model, and --allow-model-calls")
    from .adapters import ChatDecider, CoreRetriever
    from .haystack import run
    scope = Scope(args.scope, args.scope_id)
    retriever = CoreRetriever(args.api_url, scope, mode=args.mode)
    try:
        if args.username:
            retriever.login(args.username, getpass.getpass("OSII password: "))
        key = os.environ.get("OSII_RAG_MODEL_API_KEY", "")
        key_file = os.environ.get("OSII_RAG_MODEL_API_KEY_FILE", "")
        if key_file:
            key = Path(key_file).read_text().strip()
        result = run(Question(args.question, scope), retrieve=retriever,
            decide=ChatDecider(args.chat_url, args.chat_model, api_key=key), strategy=args.strategy,
            limits=Limits(max_retrievals=args.max_retrievals, max_model_calls=args.max_model_calls))
        print(json.dumps(asdict(result), indent=2))
    except StrategyError as exc:
        parser.exit(1, f"Experiment stopped: {exc}\n")
    finally:
        retriever.session.close()


if __name__ == "__main__":
    main()
