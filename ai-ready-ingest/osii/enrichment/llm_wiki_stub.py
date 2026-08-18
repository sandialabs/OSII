from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from osii.domain.artifacts.enrichment_artifacts import create_enrichment_output_dir
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.scopes import normalize_scope_type
from osii.enrichment.base import BaseEnricher, EnrichmentState

from osii.enrichment.cli_osii_to_wiki import process_one_object
from osii.enrichment.llm_wiki import LlmWiki
from collections import Counter
from osii.enrichment.common import collect_scope_texts
from osii.enrichment.stats_keywords import tokenize, DEFAULT_STOPWORDS

def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"1", "true", "yes", "y", "on"}:
            return True

        if normalized in {"0", "false", "no", "n", "off"}:
            return False

    return default


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value

    return {}

def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def _build_scope_keyword_guidance(
    *,
    osii_store: Path,
    scope: dict,
    top_k: int = 75,
    min_count: int = 2,
) -> tuple[list[dict], str, int]:
    """
    Build collection/root/folder/object-level keyword guidance.

    These keywords are used only as extraction guidance. They are not
    automatically treated as entities or concepts.
    """
    texts, total_chars = collect_scope_texts(osii_store, scope)

    counter = Counter()

    for item in texts:
        tokens = [
            token
            for token in tokenize(item.get("text") or "")
            if token not in DEFAULT_STOPWORDS
        ]
        counter.update(tokens)

    keywords = [
        {
            "term": term,
            "count": count,
        }
        for term, count in counter.most_common()
        if count >= min_count
    ][:top_k]

    if not keywords:
        return [], "", total_chars

    keyword_lines = [
        f"- `{item['term']}` count={item['count']}"
        for item in keywords
    ]

    guidance = "\n".join(
        [
            "COLLECTION/SCOPE KEYWORD GUIDANCE:",
            "",
            "The following keywords were extracted from the selected OSII scope.",
            "Use them as topical guidance when extracting entities and concepts.",
            "",
            "Important rules:",
            "- Do not treat these keywords as entities by default.",
            "- Extract an entity only if a specific, concrete, source-grounded instance appears in the source page.",
            "- A keyword may indicate that related named systems, software, datasets, people, organizations, experiments, figures, tables, or requirements are important.",
            "- Generic keywords should usually become neither entities nor concepts unless the source gives them a specific role.",
            "- Concepts should still be selective and source-grounded.",
            "",
            "Extracted scope keywords:",
            "",
            *keyword_lines,
        ]
    )

    return keywords, guidance, total_chars


def _path_from_config(value: Any, *, base: Path | None = None) -> Path | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    path = Path(text)

    if not path.is_absolute() and base is not None:
        path = base / path

    return path.resolve()

def _extract_prefixed_options(config: dict, prefix: str) -> dict:
    result = {}

    prefix_with_dot = prefix + "."

    for key, value in config.items():
        key = str(key)

        if key.startswith(prefix_with_dot):
            result[key[len(prefix_with_dot):]] = value

    return result

def _has_synthesis_artifacts(osii_store: Path, file_id: str) -> bool:
    object_dir = osii_store / "objects" / file_id
    return (object_dir / "synth.txt").exists() or (object_dir / "synth.toml").exists()


class LlmWikiStubEnricher(BaseEnricher):
    """
    Backend enrichment interface for building an LLM wiki from an OSII scope.

    This class intentionally keeps the existing class name
    `LlmWikiStubEnricher` so any current registry/import code that expects that
    class name does not break.

    The enricher no longer creates a stub bundle. It creates a real wiki using
    the existing microservices.llm_wiki code.
    """

    name = "llm_wiki"
    display_name = "LLM Wiki Enricher"
    description = (
        "Creates an LLM-maintained markdown wiki for a selected OSII scope "
        "from existing OSII synthesis artifacts."
    )
    version = "1.0"

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        enricher_config = enricher_config or {}
        state = EnrichmentState()

        try:
            osii_store = osii_store.resolve()

            scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

            if scope_type not in {"collection", "folder", "root", "object"}:
                raise ValueError(f"Unsupported scope type: {scope_type}")

            file_ids = list_scope_file_ids(osii_store, scope)
            state.input_objects_seen = len(file_ids)

            if not file_ids:
                raise ValueError("Selected scope contains no OSII objects.")

            auto_integrate = _as_bool(
                enricher_config.get("auto_integrate"),
                default=True,
            )

            skip_missing_synthesis = _as_bool(
                enricher_config.get("skip_missing_synthesis"),
                default=False,
            )

            data_root = _path_from_config(
                enricher_config.get("data_root"),
                base=osii_store.parent,
            )

            integrator_config = _as_dict(
                enricher_config.get("integrator_config")
            )

            integrator_config.update(
                _extract_prefixed_options(enricher_config, "integrator")
            )

            verbose = _as_bool(
            enricher_config.get("verbose"),
            default=True,
            )

            max_objects_raw = enricher_config.get("max_objects")
            max_objects = int(max_objects_raw) if max_objects_raw else 0
            out = create_enrichment_output_dir(
                osii_store,
                scope,
                kind="wiki",
                method=self.name,
            )

            wiki_root = Path(out["dir_path"]).resolve()
            wiki_root.mkdir(parents=True, exist_ok=True)

            scope_keyword_guidance_enabled = _as_bool(
        enricher_config.get("scope_keyword_guidance"),
        default=True,
    )

            scope_keyword_top_k = _as_int(
                enricher_config.get("scope_keyword_top_k"),
                default=75,
            )

            scope_keyword_min_count = _as_int(
                enricher_config.get("scope_keyword_min_count"),
                default=2,
            )

            scope_keywords: list[dict] = []
            scope_keyword_guidance = ""

            if scope_keyword_guidance_enabled:
                scope_keywords, scope_keyword_guidance, total_keyword_chars = _build_scope_keyword_guidance(
                    osii_store=osii_store,
                    scope=scope,
                    top_k=scope_keyword_top_k,
                    min_count=scope_keyword_min_count,
                )

                state.input_chars_read = total_keyword_chars

                if scope_keyword_guidance:
                    wiki = LlmWiki(wiki_root=wiki_root)
                    wiki.initialize()

                    wiki.append_log(
                        action="scope-keywords",
                        title=f"{out['scope_type']} | {out['scope_id']}",
                        details=[
                            "Scope-level keywords were extracted and used as auto-integration guidance.",
                            f"Keyword count: `{len(scope_keywords)}`",
                            "Keywords:",
                            ", ".join(
                                f"`{item['term']}` ({item['count']})"
                                for item in scope_keywords
                            ),
                        ],
                    )

            processed_results: list[dict] = []
            skipped_results: list[dict] = []


            effective_expert_context_parts = []

            if expert_context:
                effective_expert_context_parts.append(expert_context)

            if scope_keyword_guidance:
                effective_expert_context_parts.append(scope_keyword_guidance)

            effective_expert_context = "\n\n".join(effective_expert_context_parts) or None

            for index, file_id in enumerate(file_ids, start=1):
                if max_objects and index > max_objects:
                    if verbose:
                        print(
                            f"[llm_wiki] Reached max_objects={max_objects}; stopping early.",
                            flush=True,
                        )
                    break

                if verbose:
                    print(
                        f"[llm_wiki] Processing {index}/{len(file_ids)}: {file_id} "
                        f"auto_integrate={auto_integrate}",
                    flush=True,
                    )


                if not _has_synthesis_artifacts(osii_store, file_id):
                    skipped = {
                        "file_id": file_id,
                        "reason": "Missing synth.txt and synth.toml.",
                    }

                    if skip_missing_synthesis:
                        skipped_results.append(skipped)
                        continue

                    raise RuntimeError(
                        "OSII object is missing synthesis artifacts: "
                        f"{osii_store / 'objects' / file_id}"
                    )

                result = process_one_object(
                    file_id=file_id,
                    osii_root=osii_store,
                    wiki_root=wiki_root,
                    source_file=None,
                    data_root=data_root,
                    source_relpath=None,
                    auto_integrate=auto_integrate,
                    expert_context=effective_expert_context,
                    integrator_config=integrator_config,
                )

                processed_results.append(result)

            wiki = LlmWiki(wiki_root=wiki_root)
            wiki.initialize()
            wiki.rebuild_index()

            metadata = {
                "method": self.name,
                "version": self.version,
                "scope_type": out["scope_type"],
                "scope_id": out["scope_id"],
                "kind": out["kind"],
                "expert_context_used": bool(expert_context),
                "scope": scope,
                "config": {
                    "auto_integrate": auto_integrate,
                    "skip_missing_synthesis": skip_missing_synthesis,
                    "data_root": str(data_root) if data_root else None,
                    "integrator_config": integrator_config,
                },
                "input_object_count": len(file_ids),
                "processed_count": len(processed_results),
                "skipped_count": len(skipped_results),
                "processed_file_ids": [
                    item["file_id"] for item in processed_results
                ],
                "skipped": skipped_results,
                "results": processed_results,
            }

            metadata_path = wiki_root / "enrichment_metadata.json"
            metadata_path.write_text(
                json.dumps(metadata, indent=2),
                encoding="utf-8",
            )

            state.output_files_written = len(
                [path for path in wiki_root.rglob("*") if path.is_file()]
            )

            return {
                "ok": True,
                "result": {
                    "scope_type": out["scope_type"],
                    "scope_id": out["scope_id"],
                    "kind": out["kind"],
                    "method": out["method"],
                    "output_dir": out["relpath"],
                    "wiki_root": str(wiki_root),
                    "index": "index.md",
                    "metadata": "enrichment_metadata.json",
                    "input_object_count": len(file_ids),
                    "processed_count": len(processed_results),
                    "skipped_count": len(skipped_results),
                    "auto_integrate": auto_integrate,
                },
                "error": None,
            }

        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error) from exc
        
