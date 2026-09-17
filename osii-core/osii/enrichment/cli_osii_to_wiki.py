from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from osii.enrichment.candidates import load_or_build_document_frequency
from osii.enrichment.llm_wiki import (
    LlmWiki,
    read_text_if_exists,
    read_toml_if_exists,
    relpath_or_name,
    ensure_path_within,
    reject_symlinks_under,
    validate_file_id
)


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


def _unique_preserve_order(items: list[str]) -> list[str]:
    """
    Return unique non-empty strings while preserving the user's selected order.
    """
    seen = set()
    result = []

    for item in items:
        item = str(item).strip()

        if not item:
            continue

        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def _deep_find_string(data: Any, candidate_keys: set[str]) -> str | None:
    """
    Recursively search nested dict/list data for a likely source path/name field.

    This is intentionally best-effort because OSII metadata schemas may vary.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            key_lower = str(key).lower()

            if key_lower in candidate_keys and isinstance(value, str) and value.strip():
                return value.strip()

        for value in data.values():
            found = _deep_find_string(value, candidate_keys)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _deep_find_string(item, candidate_keys)
            if found:
                return found

    return None


def infer_source_path_from_osii_object(object_dir: Path) -> Path | None:
    """
    Try to infer the original source path from existing OSII metadata.

    meta.toml's [file] section describes the document and is authoritative when
    present. The best-effort search is only a fallback, and it deliberately
    omits the generic "name" key: provenance.toml uses that key for the
    extractor and synthesizer, so searching it first labelled every page after
    the extractor instead of the document.
    """
    provenance = read_toml_if_exists(object_dir / "provenance.toml")
    meta = read_toml_if_exists(object_dir / "meta.toml")

    file_section = meta.get("file") if isinstance(meta, dict) else None

    if isinstance(file_section, dict):
        for key in ("source_relpath", "source_path", "filename"):
            value = file_section.get(key)
            if isinstance(value, str) and value.strip():
                return Path(value.strip())

    candidate_keys = {
        "source_path",
        "source",
        "path",
        "file_path",
        "filepath",
        "input_path",
        "input_file",
        "original_path",
        "original_file",
        "filename",
        "file_name",
    }

    for data in (meta, provenance):
        found = _deep_find_string(data, candidate_keys)
        if found:
            return Path(found)

    return None


def infer_source_relpath(
    *,
    source_path: Path,
    data_root: Path | None,
    explicit_source_relpath: str | None,
) -> str:
    if explicit_source_relpath:
        return explicit_source_relpath

    if data_root:
        return relpath_or_name(data_root, source_path)

    return source_path.name


def build_empty_extract_result() -> dict:
    """
    LlmWiki.upsert_source_page only uses extract_result for its error field
    in the generated markdown block. Since extraction has already happened,
    we pass a minimal result.
    """
    return {
        "error": "",
        "note": "Loaded from existing OSII artifacts; extractor was not rerun.",
    }


def build_empty_synth_result() -> dict:
    """
    LlmWiki.upsert_source_page only uses synth_result for its error field
    in the generated markdown block. Since synthesis has already happened,
    we pass a minimal result.
    """
    return {
        "error": "",
        "note": "Loaded from existing OSII artifacts; synthesizer was not rerun.",
    }


def process_one_object(
    *,
    file_id: str,
    osii_root: Path,
    wiki_root: Path,
    source_file: Path | None,
    data_root: Path | None,
    source_relpath: str | None,
    auto_integrate: bool,
    expert_context: str | None,
    integrator_config: dict,
    integrator=None,
    document_frequency: dict[str, int] | None = None,
    corpus_size: int | None = None,
    force: bool = False,
) -> dict:
    """
    Build or refresh the wiki pages for one OSII object.

    ``integrator``, ``document_frequency``, and ``corpus_size`` may be supplied
    by a caller processing many objects. Each is derived from the corpus rather
    than from this document, so building them here would repeat corpus-wide
    work once per document.
    """
    file_id = validate_file_id(file_id)

    objects_root = (osii_root / "objects").resolve()
    object_dir = ensure_path_within(objects_root, objects_root / file_id)
    if object_dir.exists():
        reject_symlinks_under(object_dir)

    if not object_dir.exists() or not object_dir.is_dir():
        raise RuntimeError(f"OSII object directory does not exist: {object_dir}")

    synth_txt = object_dir / "synth.txt"
    synth_toml = object_dir / "synth.toml"

    if not synth_txt.exists() and not synth_toml.exists():
        raise RuntimeError(
            f"OSII object does not appear to contain synthesis artifacts: {object_dir}"
        )

    inferred_source_path = infer_source_path_from_osii_object(object_dir)

    if source_file:
        final_source_path = source_file.resolve()
    elif inferred_source_path:
        final_source_path = inferred_source_path

        if not final_source_path.is_absolute():
            if data_root:
                final_source_path = data_root / final_source_path
            else:
                final_source_path = (osii_root.parent / final_source_path).resolve()
    else:
        # Fallback if OSII metadata does not contain a source path.
        # The wiki can still be built because the important artifacts are under .osii.
        final_source_path = object_dir / f"{file_id}.source"

    if data_root:
        final_data_root = data_root.resolve()
    elif final_source_path.exists():
        final_data_root = final_source_path.parent.resolve()
    else:
        final_data_root = osii_root.parent.resolve()

    final_source_relpath = infer_source_relpath(
        source_path=final_source_path,
        data_root=final_data_root,
        explicit_source_relpath=source_relpath,
    )

    wiki = LlmWiki(wiki_root=wiki_root)
    wiki.initialize()

    record = wiki.make_record(
        file_id=file_id,
        source_path=final_source_path,
        data_root=final_data_root,
        osii_root=osii_root,
        source_relpath=final_source_relpath,
    )

    source_page = wiki.upsert_source_page(
        record=record,
        extract_result=build_empty_extract_result(),
        synth_result=build_empty_synth_result(),
    )

    integration_result = None

    if auto_integrate:
        if document_frequency is None or corpus_size is None:
            document_frequency, corpus_size = load_corpus_document_frequency(osii_root)

        if integrator is None:
            from osii.enrichment.auto_integrate import AutoWikiIntegrator

            integrator = AutoWikiIntegrator(wiki=wiki)

        # Candidates are drawn from the extracted document, not the source
        # page, which is mostly generated metadata around a short synthesis.
        integration_result = integrator.integrate_source_page(
            source_page=source_page,
            expert_context=expert_context,
            integrator_config=integrator_config,
            full_text=read_text_if_exists(record.extracted_text_path),
            document_frequency=document_frequency,
            corpus_size=corpus_size,
            force=force,
        )

    return {
        "file_id": file_id,
        "osii_object_dir": str(object_dir),
        "source_path": str(final_source_path),
        "source_relpath": final_source_relpath,
        "wiki_source_page": str(source_page),
        "integration_result": integration_result,
    }


def _process_many(
    *,
    file_ids: list[str],
    osii_root: Path,
    wiki_root: Path,
    source_file: Path | None,
    data_root: Path | None,
    source_relpath: str | None,
    auto_integrate: bool,
    expert_context: str | None,
    integrator_config: dict,
    force: bool = False,
    progress: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Run many objects through the wiki with corpus-wide work done once.

    Three things are hoisted out of the per-document path: the integrator, the
    corpus term frequencies, and the whole-wiki bookkeeping. A document that
    raises is recorded and the run continues, because a corpus run that dies on
    its eight-hundredth document should not discard the seven hundred and
    ninety-nine it already wrote.
    """
    from osii.enrichment.auto_integrate import AutoWikiIntegrator

    integrator = None
    document_frequency: dict[str, int] = {}
    corpus_size = 0

    if auto_integrate:
        wiki = LlmWiki(wiki_root=wiki_root)
        wiki.initialize()
        integrator = AutoWikiIntegrator(wiki=wiki)
        document_frequency, corpus_size = load_corpus_document_frequency(osii_root)

    results: list[dict] = []
    failures: list[dict] = []

    def run_all() -> None:
        total = len(file_ids)

        for index, file_id in enumerate(file_ids, start=1):
            if progress:
                print(f"[{index}/{total}] Updating wiki from OSII object: {file_id}")

            try:
                results.append(
                    process_one_object(
                        file_id=file_id,
                        osii_root=osii_root,
                        wiki_root=wiki_root,
                        source_file=source_file,
                        data_root=data_root,
                        source_relpath=source_relpath,
                        auto_integrate=auto_integrate,
                        expert_context=expert_context,
                        integrator_config=integrator_config,
                        integrator=integrator,
                        document_frequency=document_frequency if auto_integrate else None,
                        corpus_size=corpus_size if auto_integrate else None,
                        force=force,
                    )
                )
            except Exception as exc:
                failures.append(
                    {
                        "file_id": file_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(
                    f"ERROR: {file_id} failed and was skipped: {exc}",
                    file=sys.stderr,
                )

    if integrator is not None:
        with integrator.deferred_bookkeeping():
            run_all()
    else:
        run_all()

    return results, failures


def load_corpus_document_frequency(osii_root: Path) -> tuple[dict[str, int], int]:
    """Corpus-wide term frequencies, loaded once for a whole run."""
    objects_dir = osii_root / "objects"

    corpus_ids = [
        path.name for path in objects_dir.iterdir() if path.is_dir()
    ] if objects_dir.is_dir() else []

    return load_or_build_document_frequency(osii_root, corpus_ids)


def process_selected_osii_objects(
    *,
    file_ids: list[str],
    osii_root: Path,
    wiki_root: Path,
    data_root: Path | None = None,
    auto_integrate: bool = False,
    expert_context: str | None = None,
    integrator_config: dict | None = None,
) -> list[dict]:
    """
    Create/update an LLM-wiki from only selected OSII objects.

    This assumes extraction/synthesis has already happened and that selected
    objects live under:

        <osii_root>/objects/<file_id>/

    Each selected object should contain synth.txt or synth.toml.

    This function is useful if you want to call the selected-object workflow
    from another Python script instead of through the CLI.
    """
    integrator_config = integrator_config or {}

    osii_root = osii_root.resolve()
    wiki_root = wiki_root.resolve()
    data_root = data_root.resolve() if data_root else None

    if not osii_root.exists() or not osii_root.is_dir():
        raise RuntimeError(f"OSII root does not exist or is not a directory: {osii_root}")

    selected_file_ids = _unique_preserve_order(file_ids)

    if not selected_file_ids:
        raise ValueError("No OSII file IDs were selected.")

    results, _ = _process_many(
        file_ids=selected_file_ids,
        osii_root=osii_root,
        wiki_root=wiki_root,
        source_file=None,
        data_root=data_root,
        source_relpath=None,
        auto_integrate=auto_integrate,
        expert_context=expert_context,
        integrator_config=integrator_config,
    )

    return results


def discover_file_ids(osii_root: Path) -> list[str]:
    objects_dir = osii_root / "objects"

    if not objects_dir.exists() or not objects_dir.is_dir():
        raise RuntimeError(f"OSII objects directory does not exist: {objects_dir}")

    file_ids: list[str] = []

    for path in sorted(objects_dir.iterdir()):
        if path.is_symlink():
            continue

        if not path.is_dir():
            continue

        try:
            validate_file_id(path.name)
        except ValueError:
            continue
        
        if (path / "synth.txt").exists() or (path / "synth.toml").exists():
            file_ids.append(path.name)

    return file_ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create/update LLM-wiki source pages directly from an existing OSII "
            "directory without rerunning extraction or synthesis. You can process "
            "all OSII objects or only selected --file-id values."
        )
    )

    parser.add_argument(
        "--osii-root",
        required=True,
        help="Path to the existing .osii root.",
    )
    parser.add_argument(
        "--wiki-root",
        required=True,
        help="Path to the markdown LLM-wiki root.",
    )
    parser.add_argument(
        "--file-id",
        action="append",
        default=[],
        help=(
            "Specific OSII file_id to ingest from .osii/objects/<file_id>. "
            "Can be repeated. Required unless --all is used."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every OSII object that has synth.txt or synth.toml.",
    )
    parser.add_argument(
        "--source-file",
        default=None,
        help=(
            "Optional original source file path. Only allowed when processing "
            "one selected --file-id. Usually only needed when OSII metadata "
            "cannot infer the source path."
        ),
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help=(
            "Optional data root used to compute source relative paths. "
            "If omitted, the source file parent or osii_root parent is used."
        ),
    )
    parser.add_argument(
        "--source-relpath",
        default=None,
        help=(
            "Optional explicit source relative path. Only allowed when processing "
            "one selected --file-id. Useful if OSII metadata does not preserve "
            "the original relative path."
        ),
    )
    parser.add_argument(
        "--expert-context",
        default=None,
        help="Optional guidance passed to the auto-integrator.",
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
        "--force",
        action="store_true",
        help=(
            "Reintegrate every selected object even when its text and settings "
            "are unchanged. Without this, objects already recorded in the "
            "manifest with the same fingerprint are skipped."
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

    osii_root = Path(args.osii_root).resolve()
    wiki_root = Path(args.wiki_root).resolve()
    source_file = Path(args.source_file).resolve() if args.source_file else None
    data_root = Path(args.data_root).resolve() if args.data_root else None

    selected_file_ids = _unique_preserve_order(args.file_id)

    if not osii_root.exists() or not osii_root.is_dir():
        print(
            f"ERROR: OSII root does not exist or is not a directory: {osii_root}",
            file=sys.stderr,
        )
        return 2

    if source_file and not source_file.exists():
        print(f"WARNING: source file does not exist: {source_file}", file=sys.stderr)

    if data_root and not data_root.exists():
        print(f"WARNING: data root does not exist: {data_root}", file=sys.stderr)

    if args.all and selected_file_ids:
        print(
            "ERROR: use either --all or one/more --file-id values, not both.",
            file=sys.stderr,
        )
        return 2

    if not args.all and not selected_file_ids:
        print("ERROR: either --file-id or --all is required.", file=sys.stderr)
        return 2

    if args.all and args.source_file:
        print(
            "ERROR: --source-file can only be used with a single --file-id, not --all.",
            file=sys.stderr,
        )
        return 2

    if args.all and args.source_relpath:
        print(
            "ERROR: --source-relpath can only be used with a single --file-id, not --all.",
            file=sys.stderr,
        )
        return 2

    if source_file and len(selected_file_ids) != 1:
        print(
            "ERROR: --source-file can only be used when exactly one --file-id is selected.",
            file=sys.stderr,
        )
        return 2

    if args.source_relpath and len(selected_file_ids) != 1:
        print(
            "ERROR: --source-relpath can only be used when exactly one --file-id is selected.",
            file=sys.stderr,
        )
        return 2

    try:
        integrator_config = parse_options(args.integrator_option)
    except Exception as exc:
        print(f"ERROR: could not parse integrator options: {exc}", file=sys.stderr)
        return 2

    try:
        if args.all:
            file_ids = discover_file_ids(osii_root)
        else:
            file_ids = selected_file_ids

        results, failures = _process_many(
            file_ids=file_ids,
            osii_root=osii_root,
            wiki_root=wiki_root,
            source_file=source_file,
            data_root=data_root,
            source_relpath=args.source_relpath,
            auto_integrate=args.auto_integrate,
            expert_context=args.expert_context,
            integrator_config=integrator_config,
            force=args.force,
            progress=True,
        )

    except Exception as exc:
        # Only setup can reach here now; a failing document is recorded and the
        # run continues.
        print(f"ERROR: OSII-to-wiki update failed: {exc}", file=sys.stderr)
        return 1

    skipped = [
        result for result in results
        if (result.get("integration_result") or {}).get("skipped")
    ]

    print(
        json.dumps(
            {
                "osii_root": str(osii_root),
                "wiki_root": str(wiki_root),
                "processed_count": len(results),
                "skipped_count": len(skipped),
                "failed_count": len(failures),
                "processed_file_ids": file_ids,
                "failures": failures,
                "results": results,
            },
            indent=2,
        )
    )

    if failures:
        print(
            f"\n{len(failures)} of {len(file_ids)} objects failed; "
            f"{len(results) - len(skipped)} integrated, {len(skipped)} skipped as unchanged.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
