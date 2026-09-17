from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from osii.domain.storage.store import ensure_osii_store_layout
from osii.extraction.textract_extractor import TextractExtractor
from osii.extraction.tika_extractor import TikaCatchallExtractor
from osii.synthesis.file.describe import DescribeSynthesizer
from osii.enrichment.llm_wiki import LlmWiki, relpath_or_name


def parse_options(option_list: list[str]) -> dict:
    result = {}

    for item in option_list:
        if "=" not in item:
            raise ValueError(f"Invalid option '{item}', expected key=value")

        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(f"Invalid option '{item}', empty key")

        result[key] = value

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Textract extraction, Describe synthesis, create/update "
            "an LLM-wiki source page, and optionally auto-populate entities/concepts."
        )
    )

    parser.add_argument(
        "--source-file",
        required=True,
        help="Path to the source file to ingest.",
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="Root path used to compute source relative paths.",
    )
    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the .osii root.",
    )
    parser.add_argument(
        "--wiki-root",
        required=True,
        help="Path to the markdown LLM-wiki root.",
    )
    parser.add_argument(
        "--expert-context",
        default=None,
        help="Optional guidance passed to the extractor, synthesizer, and wiki integrator.",
    )
    parser.add_argument(
        "--textract-option",
        action="append",
        default=[],
        help=(
            "Textract extractor option in key=value form. Repeatable. "
            "Example: --textract-option max_words=2000"
        ),
    )
    parser.add_argument(
        "--tika-option",
        action="append",
        default=[],
        help=(
            "Tika extractor option in key=value form. Repeatable. "
            # "Example: --textract-option max_words=2000"
        ),
    )
    parser.add_argument(
        "--describe-option",
        action="append",
        default=[],
        help=(
            "Describe synthesizer option in key=value form. Repeatable. "
            "Example: --describe-option model=openai/gpt-oss-120b"
        ),
    )
    parser.add_argument(
        "--auto-integrate",
        action="store_true",
        help=(
            "After creating the source page, call an LLM to identify entities/concepts "
            "and create/update wiki/entities and wiki/concepts pages."
        ),
    )
    parser.add_argument(
        "--integrator-option",
        action="append",
        default=[],
        help=(
            "Auto-integrator option in key=value form. Repeatable. "
            "Examples: --integrator-option model=openai/gpt-oss-120b "
            "--integrator-option max_source_chars=30000"
        ),
    )

    args = parser.parse_args()

    source_file = Path(args.source_file).resolve()
    data_root = Path(args.data_root).resolve()
    osii_root = Path(args.osii_root).resolve()
    wiki_root = Path(args.wiki_root).resolve()

    if not source_file.exists() or not source_file.is_file():
        print(
            f"ERROR: source file does not exist or is not a file: {source_file}",
            file=sys.stderr,
        )
        return 2

    if not data_root.exists() or not data_root.is_dir():
        print(
            f"ERROR: data root does not exist or is not a directory: {data_root}",
            file=sys.stderr,
        )
        return 2

    try:
        textract_config = parse_options(args.textract_option)
        tika_config = parse_options(args.tika_option)
        describe_config = parse_options(args.describe_option)
        integrator_config = parse_options(args.integrator_option)
    except Exception as exc:
        print(f"ERROR: could not parse options: {exc}", file=sys.stderr)
        return 2

    integration_result = None

    try:
        osii_root.mkdir(parents=True, exist_ok=True)
        wiki_root.mkdir(parents=True, exist_ok=True)
        ensure_osii_store_layout(osii_root)

        source_relpath = relpath_or_name(data_root, source_file)

        print(f"Extracting with textract: {source_file}")
        extractor = TextractExtractor()
        extract_result = extractor.extract(
            source_path=source_file,
            data_volume_root=data_root,
            osii_store=osii_root,
            expert_context=args.expert_context,
            extractor_config=textract_config,
        )
        # extractor = TikaCatchallExtractor()
        # extract_result = extractor.extract(
        #     source_path=source_file,
        #     data_volume_root=data_root,
        #     osii_store=osii_root,
        #     expert_context=args.expert_context,
        #     extractor_config=tika_config,
        # )

        file_id = extract_result["file_id"]

        print(f"Synthesizing with describe: {file_id}")
        synthesizer = DescribeSynthesizer()
        synth_result = synthesizer.synthesize(
            osii_store=osii_root,
            file_id=file_id,
            expert_context=args.expert_context,
            synthesizer_config=describe_config,
        )

        print(f"Updating LLM-wiki source page: {wiki_root}")
        wiki = LlmWiki(wiki_root=wiki_root)
        wiki.initialize()

        record = wiki.make_record(
            file_id=file_id,
            source_path=source_file,
            data_root=data_root,
            osii_root=osii_root,
            source_relpath=source_relpath,
        )

        source_page = wiki.upsert_source_page(
            record=record,
            extract_result=extract_result,
            synth_result=synth_result,
        )

        if args.auto_integrate:
            print(f"Auto-integrating entities/concepts from source page: {source_page}")

            from osii.enrichment.auto_integrate import AutoWikiIntegrator

            integrator = AutoWikiIntegrator(wiki=wiki)
            integration_result = integrator.integrate_source_page(
                source_page=source_page,
                expert_context=args.expert_context,
                integrator_config=integrator_config,
            )

    except Exception as exc:
        print(f"ERROR: LLM-wiki ingest failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "source_file": str(source_file),
                "source_relpath": source_relpath,
                "osii_root": str(osii_root),
                "wiki_root": str(wiki_root),
                "file_id": file_id,
                "extract_result": extract_result,
                "synth_result": synth_result,
                "wiki_source_page": str(source_page),
                "integration_result": integration_result,
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())