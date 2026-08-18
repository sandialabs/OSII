

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
import hashlib

from shirty.client import ShirtyClient

from osii.enrichment.llm_wiki import (
    LlmWiki,
    read_text_if_exists,
    slugify,
    utc_today,
    yaml_string,
)


DEFAULT_MODEL = "openai/gpt-oss-120b"

GENERIC_ENTITY_NAMES = {
    "software",
    "model",
    "dataset",
    "database",
    "experiment",
    "test",
    "simulation",
    "component",
    "system",
    "subsystem",
    "hardware",
    "device",
    "instrument",
    "sensor",
    "organization",
    "facility",
    "project",
    "program",
    "document",
    "publication",
    "standard",
    "requirement",
    "material",
    "chemical",
    "sample",
    "specimen",
    "method",
    "process",
    "approach",
    "technique",
    "analysis",
    "results",
    "discussion",
    "conclusion",
    "introduction",
    "background",
}
ALLOWED_ENTITY_TYPES = (
    "person",
    "organization",
    "facility",
    "project",
    "program",
    "software",
    "model",
    "dataset",
    "database",
    "instrument",
    "sensor",
    "component",
    "system",
    "subsystem",
    "hardware",
    "device",
    "material",
    "chemical",
    "sample",
    "specimen",
    "experiment",
    "test",
    "simulation",
    "document",
    "publication",
    "standard",
    "requirement",
    "location",
    "event",
    "mission",
    "contract",
    "other",
)


ENTITY_TYPE_ALIASES = {
    "company": "organization",
    "institution": "organization",
    "lab": "organization",
    "laboratory": "organization",
    "national laboratory": "organization",

    "code": "software",
    "application": "software",
    "tool": "software",
    "package": "software",
    "library": "software",

    "ml model": "model",
    "machine learning model": "model",
    "ai model": "model",
    "physics model": "model",
    ""

    "data set": "dataset",
    "data": "dataset",
    "corpus": "dataset",

    "db": "database",

    "apparatus": "instrument",
    "measurement instrument": "instrument",

    "detector": "sensor",
    "probe": "sensor",

    "part": "component",
    "module": "component",

    "platform": "system",
    "assembly": "system",

    "machine": "hardware",
    "equipment": "hardware",

    "sub-system": "subsystem",

    "substance": "chemical",
    "compound": "chemical",

    "specimen": "sample",

    "trial": "experiment",
    "study": "experiment",

    "calculation": "simulation",
    "experiment" : "simulation",

    "paper": "publication",
    "article": "publication",
    "journal article": "publication",
    "conference paper": "publication",

    "report": "document",
    "manual": "document",
    "guide": "document",

    "specification": "standard",
    "protocol": "standard",

    "req": "requirement",

    "site": "location",
    "place": "location",
}


ENTITY_DENSITY_INSTRUCTIONS = {
    "minimal": """
Extract only the most central durable entities.
Prefer precision over recall.
Aim for approximately 5-15 entities if the source supports that many.
""",
    "balanced": """
Extract the important named reusable entities.
Balance precision and recall.
Include major named organizations, people, software, models, datasets, facilities,
projects, experiments, systems, components, standards, documents, and instruments.
Aim for approximately 10-40 entities if the source supports that many.
""",
    "comprehensive": """
Extract entities comprehensively.
Prefer recall over precision, but do not invent entities.
Include major and minor named entities if they are explicitly present in the source.
Include named organizations, people, facilities, projects, programs, software,
models, datasets, databases, instruments, sensors, components, systems,
subsystems, hardware, devices, materials, chemicals, samples, experiments,
tests, simulations, documents, publications, standards, requirements, locations,
events, missions, and contracts.
Aim for approximately 20-100 entities if the source supports that many.
Use confidence "low" for uncertain cases rather than omitting them.
""",
    "exhaustive": """
Extract entities exhaustively.
Prefer high recall.
Include every explicitly named, specific, reusable entity in the source.
Include minor named entities, abbreviations, versioned items, identifiers,
named components, named materials, named parameters if uniquely identified,
standards, reports, datasets, software packages, facilities, instruments,
experiments, simulations, tests, projects, and organizations.
Do not include generic noun phrases unless they are uniquely named or identified.
Use confidence "low" for uncertain cases.
""",

"detailed_specific": """
Extract many entities, but only if they are specific, concrete, identifiable,
and directly grounded in the source.

Prefer high recall for specific entities.
Do not extract generalized ideas, broad categories, methods, themes, or vague noun phrases.

Include:
- Named people.
- Named organizations.
- Named facilities.
- Named projects and programs.
- Named software packages, codes, tools, and libraries.
- Named models.
- Named datasets and databases.
- Named instruments, sensors, detectors, machines, and apparatuses.
- Named systems, subsystems, components, parts, assemblies, and test articles.
- Named materials, chemicals, samples, and specimens.
- Named experiments, tests, simulations, runs, trials, cases, scenarios, and configurations.
- Named documents, reports, publications, standards, specifications, requirements, figures, tables, and appendices.
- Named locations, sites, events, missions, and contracts.
- Specific identifiers, report numbers, version numbers, run IDs, sample IDs, component IDs, requirement IDs, model IDs, dataset IDs, table numbers, figure numbers, and section numbers.

Do not include:
- Generic noun phrases.
- Broad scientific concepts.
- Methods unless they are specifically named.
- Entity categories such as "software", "model", "dataset", or "experiment" by themselves.
- General topics, risks, processes, themes, or mechanisms.
- Implied entities that are not explicitly present in the source.

For every entity, include detailed source-grounded information:
- What it is.
- Why it appears in the source.
- Its role or relationship to the source.
- Relevant aliases, identifiers, versions, labels, or abbreviations.
- Location in the source when available.
- Evidence phrase or exact quote.
- Confidence level.

Aim to extract as many specific entities as the source supports, but reject vague or generalized entities.
""",
}


def stable_uid(*parts: Any, prefix: str = "wiki") -> str:
    """
    Create a stable deterministic UID from text parts.

    Same inputs always produce the same UID.
    """
    raw = "::".join(str(part or "").strip().lower() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def entity_uid(
    *,
    source_namespace: str,
    entity_type: str,
    name: str,
) -> str:
    return stable_uid(
        "entity",
        source_namespace,
        entity_type,
        name,
        prefix="ent",
    )


def concept_uid(
    *,
    source_namespace: str,
    name: str,
) -> str:
    return stable_uid(
        "concept",
        source_namespace,
        name,
        prefix="con",
    )


def page_uid(
    *,
    kind: str,
    source_namespace: str,
) -> str:
    return stable_uid(
        "page",
        kind,
        source_namespace,
        prefix="page",
    )


def _msg_content(msg) -> str:
    if msg is None:
        return ""
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return getattr(msg, "content", None) or ""


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines).strip()

    return text


def _extract_json_object(text: str) -> str:
    """
    Best-effort extraction of the first JSON object from model output.
    """
    text = _strip_code_fences(text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")

    return text[start:end + 1]


def _parse_json_or_raise(raw: str) -> dict[str, Any]:
    payload = _extract_json_object(raw)
    data = json.loads(payload)

    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object.")

    return data


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

def normalize_entity_type(value: Any) -> str:
    """
    Normalize model-provided entity types into the allowed taxonomy.
    """
    raw = _clean_string(value).lower()
    raw = raw.replace("_", " ").replace("-", " ").strip()

    if not raw:
        return "other"

    mapped = ENTITY_TYPE_ALIASES.get(raw, raw)
    mapped = mapped.replace("_", " ").replace("-", " ").strip()

    candidate = mapped.replace(" ", "_")

    if candidate in ALLOWED_ENTITY_TYPES:
        return candidate

    slug_candidate = slugify(mapped, fallback="other").replace("-", "_")

    if slug_candidate in ALLOWED_ENTITY_TYPES:
        return slug_candidate

    return "other"


def entity_density_instruction(mode: Any) -> str:
    mode_clean = _clean_string(mode).lower() or "balanced"
    return ENTITY_DENSITY_INSTRUCTIONS.get(
        mode_clean,
        ENTITY_DENSITY_INSTRUCTIONS["balanced"],
    )


def _entity_key_text(value: Any) -> str:
    """
    Normalize an entity name or alias for deduplication.
    """
    text = _clean_string(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _entity_keys(entity: dict[str, Any]) -> set[tuple[str, str]]:
    entity_type = normalize_entity_type(entity.get("entity_type"))
    keys: set[tuple[str, str]] = set()

    name_key = _entity_key_text(entity.get("name"))

    if name_key:
        keys.add((entity_type, name_key))

    for alias in _as_list(entity.get("aliases")):
        alias_key = _entity_key_text(alias)

        if alias_key:
            keys.add((entity_type, alias_key))

    return keys


def _merge_unique_list_values(*values: Any) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []

    for value in values:
        for item in _as_list(value):
            cleaned = _clean_string(item)

            if not cleaned:
                continue

            key = cleaned.lower()

            if key in seen:
                continue

            seen.add(key)
            merged.append(cleaned)

    return merged


def _merge_unique_text(existing: Any, incoming: Any, *, separator: str = "; ") -> str:
    existing_clean = _clean_string(existing)
    incoming_clean = _clean_string(incoming)

    if not existing_clean:
        return incoming_clean

    if not incoming_clean:
        return existing_clean

    if incoming_clean.lower() in existing_clean.lower():
        return existing_clean

    return f"{existing_clean}{separator}{incoming_clean}"


def _best_confidence(existing: Any, incoming: Any) -> str:
    order = {
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    existing_clean = _clean_string(existing).lower()
    incoming_clean = _clean_string(incoming).lower()

    if order.get(incoming_clean, 0) > order.get(existing_clean, 0):
        return incoming_clean

    return existing_clean or incoming_clean




def looks_specific_entity_name(name: Any) -> bool:
    """
    Heuristic filter for rejecting overly generic entity names.

    This keeps named, numbered, acronym-like, versioned, or otherwise
    identifiable strings and rejects broad generic nouns.
    """
    text = _clean_string(name)

    if not text:
        return False

    normalized = re.sub(r"\s+", " ", text).strip().lower()

    if normalized in GENERIC_ENTITY_NAMES:
        return False

    # Reject very short generic lowercase words.
    # if len(normalized.split()) == 1 and normalized.islower() and len(normalized) < 5:
    #     return False
    if normalized in GENERIC_ENTITY_NAMES:
        return False
    
    # Keep if it contains digits, useful for IDs, versions, figures, tables, runs, etc.
    if re.search(r"\d", text):
        return True

    # Keep acronym-like names.
    if re.search(r"\b[A-Z]{2,}\b", text):
        return True

    # Keep CamelCase or mixed-case technical names.
    if re.search(r"[a-z][A-Z]|[A-Z][a-z]", text):
        return True

    # Keep names with separators common in identifiers.
    if re.search(r"[-_/.:#]", text):
        return True

    # Keep multi-word proper-name-like strings.
    words = text.split()

    if len(words) >= 2 and any(word[:1].isupper() for word in words):
        return True

    # Keep longer multi-word noun phrases only if they look labeled/specific.
    if len(words) >= 3 and re.search(
        r"\b(system|facility|laboratory|lab|project|program|model|dataset|database|"
        r"software|code|tool|instrument|sensor|detector|component|assembly|sample|"
        r"specimen|experiment|test|trial|run|case|scenario|report|standard|"
        r"specification|requirement|appendix|table|figure|section)\b",
        normalized,
    ):
        return True

    return False


def filter_specific_entities(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for entity in entities:
        name = _clean_string(entity.get("name"))

        if not looks_specific_entity_name(name):
            continue

        evidence = _clean_string(entity.get("evidence"))

        # Require evidence so generic hallucinated entities are less likely.
        if not evidence:
            continue

        filtered.append(entity)

    return filtered



def _merge_entity(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two records believed to describe the same entity.
    """
    merged = dict(existing)

    existing_name = _clean_string(existing.get("name"))
    incoming_name = _clean_string(incoming.get("name"))

    aliases = _merge_unique_list_values(
        existing.get("aliases"),
        incoming.get("aliases"),
    )

    if incoming_name and incoming_name.lower() != existing_name.lower():
        aliases = _merge_unique_list_values(aliases, [incoming_name])

    if aliases:
        merged["aliases"] = aliases

    existing_summary = _clean_string(existing.get("summary"))
    incoming_summary = _clean_string(incoming.get("summary"))

    if len(incoming_summary) > len(existing_summary):
        merged["summary"] = incoming_summary

    merged["evidence"] = _merge_unique_text(
        existing.get("evidence"),
        incoming.get("evidence"),
    )

    merged["page"] = _merge_unique_text(
        existing.get("page"),
        incoming.get("page"),
    )

    merged["notes"] = _merge_unique_text(
        existing.get("notes"),
        incoming.get("notes"),
    )

    merged["confidence"] = _best_confidence(
        existing.get("confidence"),
        incoming.get("confidence"),
    )

    for field in ("value", "unit"):
        if not _clean_string(merged.get(field)) and _clean_string(incoming.get(field)):
            merged[field] = _clean_string(incoming.get(field))

    merged["entity_type"] = normalize_entity_type(
        merged.get("entity_type") or incoming.get("entity_type")
    )

    return merged


def normalize_and_deduplicate_entities(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize entity types and merge likely duplicates.

    Duplicates are detected using entity type plus canonical name or aliases.
    """
    deduped: list[dict[str, Any]] = []
    key_to_index: dict[tuple[str, str], int] = {}

    for raw_entity in entities:
        if not isinstance(raw_entity, dict):
            continue

        entity = dict(raw_entity)

        name = _clean_string(entity.get("name"))

        if not name:
            continue

        entity["name"] = name
        entity["entity_type"] = normalize_entity_type(entity.get("entity_type"))

        aliases = [
            _clean_string(alias)
            for alias in _as_list(entity.get("aliases"))
            if _clean_string(alias)
        ]

        if aliases:
            entity["aliases"] = aliases

        keys = _entity_keys(entity)

        matching_index = None

        for key in keys:
            if key in key_to_index:
                matching_index = key_to_index[key]
                break

        if matching_index is None:
            deduped.append(entity)
            new_index = len(deduped) - 1

            for key in keys:
                key_to_index[key] = new_index

            continue

        deduped[matching_index] = _merge_entity(
            deduped[matching_index],
            entity,
        )

        for key in _entity_keys(deduped[matching_index]):
            key_to_index[key] = matching_index

    return deduped


def _markdown_bullets(items: list[str], default: str = "- TBD") -> str:
    cleaned = [_clean_string(item) for item in items if _clean_string(item)]
    if not cleaned:
        return default
    return "\n".join(f"- {item}" for item in cleaned)


def source_namespace_from_page(source_page: Path) -> str:
    """
    Derive the per-source folder name for concepts/entities.

    Example:
        wiki/sources/paper1-sha256-abc123.md

    Produces:
        paper1-sha256-abc123

    This creates:
        wiki/concepts/paper1-sha256-abc123/
        wiki/entities/paper1-sha256-abc123/
    """
    return slugify(source_page.stem, fallback="source")


def wiki_link_for_path(wiki_root: Path, path: Path) -> str:
    rel = path.resolve().relative_to(wiki_root.resolve()).as_posix()
    return f"[[{rel}]]"


def replace_markdown_section(text: str, heading: str, new_body: str) -> str:
    """
    Replace a level-2 markdown section.

    Example section:

        ## Key claims and facts

        old body

    becomes:

        ## Key claims and facts

        new body
    """
    escaped_heading = re.escape(heading)
    pattern = rf"(^## {escaped_heading}\s*\n)(.*?)(?=^## |\Z)"

    replacement = f"## {heading}\n\n{new_body.strip()}\n\n"

    if re.search(pattern, text, flags=re.MULTILINE | re.DOTALL):
        return re.sub(
            pattern,
            replacement,
            text,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )

    return text.rstrip() + "\n\n" + replacement


def ensure_source_grounding_bullet(
    *,
    page_text: str,
    source_link: str,
    evidence: str,
) -> str:
    bullet = f"- {source_link}"
    if evidence:
        bullet += f" — {evidence}"

    if bullet in page_text or source_link in page_text:
        return page_text

    if "## Source grounding" not in page_text:
        return page_text.rstrip() + f"\n\n## Source grounding\n\n{bullet}\n"

    pattern = r"(^## Source grounding\s*\n)(.*?)(?=^## |\Z)"

    def repl(match: re.Match) -> str:
        header = match.group(1)
        body = match.group(2).strip()
        if body:
            return f"{header}\n{body}\n{bullet}\n\n"
        return f"{header}\n{bullet}\n\n"

    return re.sub(
        pattern,
        repl,
        page_text,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )

class AutoWikiIntegrator:
    """
    Uses an LLM to identify entities/concepts from a generated source page,
    then creates or updates markdown pages under source-specific folders:

        wiki/entities/<source-namespace>/*.md
        wiki/concepts/<source-namespace>/*.md
        wiki/notes/<source-namespace>.md

    Entity and concept pages are updated conservatively:
    - New pages are created if missing.
    - Existing pages are not overwritten.
    - Existing pages only get missing source-grounding bullets added.
    - Placeholder summaries may be replaced if still empty.

    Notes pages are user-maintained:
    - Created if missing.
    - Existing notes pages are not rewritten.
    - Only missing source-grounding links are added.
    """

    def __init__(self, *, wiki: LlmWiki):
        self.wiki = wiki

    def _call_model(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
    ) -> str:
        client = ShirtyClient()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        msg = completion.choices[0].message if completion and completion.choices else None
        return (_msg_content(msg) or "").strip()
    
    def document_entities_page_path(
    self,
    *,
    source_namespace: str,
) -> Path:
        namespace_slug = slugify(source_namespace, fallback="source")
        return self.wiki.entities_dir / f"{namespace_slug}.md"


    def document_concepts_page_path(
        self,
        *,
        source_namespace: str,
    ) -> Path:
        namespace_slug = slugify(source_namespace, fallback="source")
        return self.wiki.concepts_dir / f"{namespace_slug}.md"
    
    def _group_entities_by_type(
    self,
    *,
    entities: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}

        for entity in entities:
            name = _clean_string(entity.get("name"))

            if not name:
                continue

            entity_type = normalize_entity_type(entity.get("entity_type"))
            entity["entity_type"] = entity_type

            grouped.setdefault(entity_type, []).append(entity)

        return dict(sorted(grouped.items(), key=lambda item: item[0]))
    
    
    def _render_entities_document_body(
    self,
    *,
    source_namespace: str,
    entities: list[dict[str, Any]],
) -> str:
        if not entities:
            return "_No entities identified for this document._"

        grouped = self._group_entities_by_type(entities=entities)

        lines: list[str] = []

        for entity_type, items in grouped.items():
            lines.append(f"## {entity_type}")
            lines.append("")

            for entity in items:
                name = _clean_string(entity.get("name"))
                summary = _clean_string(entity.get("summary"))
                evidence = _clean_string(entity.get("evidence"))

                if not name:
                    continue

                uid = entity_uid(
                    source_namespace=source_namespace,
                    entity_type=entity_type,
                    name=name,
                )

                lines.append(f"### {name}")
                lines.append("")
                lines.append(f"- UID: `{uid}`")
                lines.append(f"- Entity type: `{entity_type}`")

                if summary:
                    lines.append(f"- Summary: {summary}")
                else:
                    lines.append("- Summary: _No summary available._")

                if evidence:
                    lines.append(f"- Evidence: {evidence}")

                aliases = [
                    _clean_string(x)
                    for x in _as_list(entity.get("aliases"))
                    if _clean_string(x)
                ]

                if aliases:
                    lines.append("- Aliases:")
                    for alias in aliases:
                        lines.append(f"  - `{alias}`")

                value = _clean_string(entity.get("value"))
                unit = _clean_string(entity.get("unit"))
                page = _clean_string(entity.get("page"))
                confidence = _clean_string(entity.get("confidence"))
                notes = _clean_string(entity.get("notes"))

                if value or unit or page or confidence or notes:
                    lines.append("- Structured attributes:")

                    if value:
                        lines.append(f"  - Value: `{value}`")

                    if unit:
                        lines.append(f"  - Unit: `{unit}`")

                    if page:
                        lines.append(f"  - Page/location: `{page}`")

                    if confidence:
                        lines.append(f"  - Confidence: `{confidence}`")

                    if notes:
                        lines.append(f"  - Notes: {notes}")

                lines.append("")

        return "\n".join(lines).strip() or "_No entities identified for this document._"
    

    def _render_concepts_document_body(
    self,
    *,
    source_namespace: str,
    concepts: list[dict[str, Any]],
) -> str:
        if not concepts:
            return "_No concepts identified for this document._"

        lines: list[str] = []

        for index, concept in enumerate(concepts, start=1):
            name = _clean_string(concept.get("name"))
            summary = _clean_string(concept.get("summary"))
            evidence = _clean_string(concept.get("evidence"))

            if not name:
                continue

            uid = concept_uid(
                source_namespace=source_namespace,
                name=name,
            )

            lines.append(f"## {index}. {name}")
            lines.append("")
            lines.append(f"- UID: `{uid}`")
            lines.append("")

            if summary:
                lines.append(summary)
            else:
                lines.append("_No summary available._")

            lines.append("")

            if evidence:
                lines.append(f"- Evidence: {evidence}")
                lines.append("")

        return "\n".join(lines).strip() or "_No concepts identified for this document._"
   

    def integrate_source_page(
        self,
        *,
        source_page: Path,
        expert_context: str | None = None,
        integrator_config: dict | None = None,
    ) -> dict:
        integrator_config = integrator_config or {}

        model = integrator_config.get("model", DEFAULT_MODEL)
        max_source_chars = int(integrator_config.get("max_source_chars", 30000))
        max_tokens = int(integrator_config.get("max_tokens", 6000))

        entity_density = integrator_config.get("entity_density", "comprehensive")
        entity_density_text = entity_density_instruction(entity_density)
        allowed_entity_types_text = " | ".join(ALLOWED_ENTITY_TYPES)

        # print(entity_density_text)
        # print(allowed_entity_types_text)

        self.wiki.initialize()

        source_page = source_page.resolve()
        source_text = read_text_if_exists(source_page)

        if not source_text:
            raise RuntimeError(f"Source page is empty or missing: {source_page}")

        source_rel = source_page.relative_to(self.wiki.wiki_root).as_posix()
        source_link = f"[[{source_rel}]]"

        source_namespace = source_namespace_from_page(source_page)
        source_excerpt = source_text[:max_source_chars]

        system = """You are an LLM-wiki maintainer.

Your job is to read one source page and extract durable wiki updates.

Return JSON only. Do not use markdown fences. Do not include prose outside JSON.

You must not invent facts. If something is uncertain, include it in caveats.
"""

        user = f"""Read the following source page and identify durable wiki updates.

EXPERT CONTEXT:
{expert_context or "No additional guidance provided."}

How to use EXPERT CONTEXT:
- Expert context may include collection-level keywords or vocabulary.
- Use those terms only as guidance for what to pay attention to.
- Do not extract a keyword as an entity unless the source page explicitly contains a specific, concrete, identifiable instance.
- Keywords can help prioritize related named software, datasets, experiments, figures, tables, components, people, organizations, requirements, or concepts.
- Source evidence always overrides keyword guidance.

SOURCE PAGE PATH:
{source_rel}

SOURCE NAMESPACE:
{source_namespace}

SOURCE PAGE CONTENT:
{source_excerpt}

Return JSON with this exact shape:

{{
  "source_summary": "One concise paragraph summarizing the source.",
  "key_claims": [
    "Durable source-grounded claim 1",
    "Durable source-grounded claim 2"
  ],
    "entities": [
    {{
      "name": "Canonical specific entity name",
      "aliases": [
        "Alternative name",
        "Acronym",
        "Identifier",
        "Versioned name"
      ],
      "entity_type": "{allowed_entity_types_text}",
      "summary": "Detailed source-grounded summary explaining exactly what this entity is, how it appears in the source, its role, and any relevant relationships or limitations.",
      "evidence": "Short exact quote or close source phrase supporting this entity.",
      "page": "Page, section, table, figure, paragraph, appendix, equation, listing, or other source location if available.",
      "confidence": "high | medium | low",
      "value": "Numeric, symbolic, label, identifier, version, or short value if applicable; otherwise empty string.",
      "unit": "Unit associated with value if applicable; otherwise empty string.",
      "notes": "Specificity notes, ambiguity, relationship to other entities, disambiguation, or caveats."
    }}
  ],
  "concepts": [
    {{
      "name": "Concept name",
      "summary": "A detailed source-grounded summary of this concept, approximately 1000 words. Explain what the concept means in this source, why it matters, how it is used, and any limitations or caveats mentioned in the source.",
      "evidence": "Brief evidence phrase from the source."
    }}
  ],
  "caveats": [
    "Caveat, uncertainty, contradiction, or limitation"
  ]
}}

Entity extraction rules:
{entity_density_text}

Entity specificity requirements:
- Every entity must be specific, concrete, and identifiable from the source.
- Prefer entities with names, labels, IDs, acronyms, version numbers, table numbers, figure numbers, run numbers, sample IDs, component IDs, model IDs, report numbers, or other identifiers.
- If the candidate entity could appear as a generic dictionary noun phrase, do not extract it unless the source uniquely names or identifies it.
- Do not extract broad topics, scientific concepts, processes, methods, or risks as entities.
- Do not extract categories like "software", "dataset", "model", "experiment", "facility", "component", or "organization" unless a specific named instance is given.
- Do not create an entity for a general material, method, or parameter unless it is specifically named, uniquely identified, labeled, numbered, or central as a concrete source object.
- If uncertain whether something is a concept or an entity, classify it as a concept unless it has a specific name, identifier, or concrete source role.

High-recall requirement:
- Extract many specific entities.
- Do not stop after only the most important entities.
- Include minor named or identified entities if they are source-grounded and useful for search or retrieval.
- Include specific figures, tables, appendices, report numbers, software versions, run IDs, sample IDs, model names, dataset names, components, instruments, tests, and configurations when present.

Evidence requirement:
- Every entity must include a short evidence phrase or exact quote from the source.
- Every entity must include a confidence value: "high", "medium", or "low".
- Use confidence "low" for specific but ambiguous entities.
- Do not include entities with no source evidence.

Use only these entity_type values:
{allowed_entity_types_text}

Concept extraction rules:
- Create concepts only for reusable ideas, methods, processes, themes, or risks.
- Keep concepts selective and high-value.
- Do not turn every entity into a concept.

Concept summary rules:
- Each concept summary should be approximately 1000 words.
- Use only information grounded in the source page.
- Include the concept's meaning, role in the source, relevant context, and limitations.
- Do not add outside background knowledge unless it is explicitly present in the source.
"""

        raw = self._call_model(
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )

        try:
            data = _parse_json_or_raise(raw)
        except Exception:
            retry_user = user + """

Your previous response was not valid JSON.

Return valid JSON only.
No markdown fences.
No commentary.
"""
            raw = self._call_model(
                model=model,
                system=system,
                user=retry_user,
                max_tokens=max_tokens,
            )
            data = _parse_json_or_raise(raw)

        result = self.apply_integration_data(
            source_page=source_page,
            source_link=source_link,
            source_namespace=source_namespace,
            data=data,
        )

        self.wiki.rebuild_index()

        self.wiki.append_log(
            action="auto-integrate",
            title=source_page.name,
            details=[
                f"Source page: `{source_rel}`",
                f"Source namespace: `{source_namespace}`",
                f"Entities page: `{result.get('entities_page')}`",
                f"Concepts page: `{result.get('concepts_page')}`",
                f"Entities extracted: {result.get('entity_count', 0)}",
                f"Concepts extracted: {result.get('concept_count', 0)}",
                f"Notes page: `{result.get('notes_page')}`",
                f"Manifest: `{result.get('manifest')}`",
                f"Concept manifest: `{result.get('concept_manifest')}`",
            ],
        )

        return result



    def entity_page_path(
        self,
        *,
        name: str,
        entity_type: str,
        source_namespace: str,
    ) -> Path:
        # entity_type_slug = slugify(entity_type or "entity", fallback="entity")
        entity_type_slug = slugify(normalize_entity_type(entity_type),fallback="entity")
        name_slug = slugify(name, fallback="unnamed")
        namespace_slug = slugify(source_namespace, fallback="source")

        return self.wiki.entities_dir / namespace_slug / f"{entity_type_slug}-{name_slug}.md"

    def concept_page_path(
        self,
        *,
        name: str,
        source_namespace: str,
    ) -> Path:
        name_slug = slugify(name, fallback="unnamed")
        namespace_slug = slugify(source_namespace, fallback="source")

        return self.wiki.concepts_dir / namespace_slug / f"{name_slug}.md"

    def notes_page_path(
        self,
        *,
        source_namespace: str,
    ) -> Path:
        namespace_slug = slugify(source_namespace, fallback="source")

        notes_dir = getattr(
            self.wiki,
            "notes_dir",
            self.wiki.wiki_root / "notes",
        )

        return notes_dir / f"{namespace_slug}.md"

#     def upsert_entity_page(
#         self,
#         *,
#         entity: dict[str, Any],
#         source_link: str,
#         source_namespace: str,
#     ) -> Path:
#         name = _clean_string(entity.get("name"))
#         entity_type = _clean_string(entity.get("entity_type")) or "other"
#         summary = _clean_string(entity.get("summary"))
#         evidence = _clean_string(entity.get("evidence"))

#         path = self.entity_page_path(
#             name=name,
#             entity_type=entity_type,
#             source_namespace=source_namespace,
#         )
#         path.parent.mkdir(parents=True, exist_ok=True)

#         if not path.exists():
#             text = f"""---
# title: {yaml_string(name)}
# kind: entity
# entity_type: {yaml_string(entity_type)}
# source_namespace: {yaml_string(source_namespace)}
# created_utc: {yaml_string(utc_today())}
# tags:
#   - entity
#   - {slugify(entity_type, fallback="other")}
# ---

# # {name}

# ## Summary

# {summary or "_No summary available yet._"}

# ## Entity type

# `{entity_type}`

# ## Source grounding

# - {source_link}

# ## Related concepts

# - TBD

# ## Related entities

# - TBD

# """
#         else:
#             text = path.read_text(encoding="utf-8", errors="replace")
#             text = ensure_source_grounding_bullet(
#                 page_text=text,
#                 source_link=source_link,
#                 evidence=evidence,
#             )

#             if "_No summary available yet._" in text and summary:
#                 text = text.replace("_No summary available yet._", summary, 1)

#         path.write_text(text.rstrip() + "\n", encoding="utf-8")
#         return path


    def upsert_entity_page(
    self,
    *,
    entity: dict[str, Any],
    source_link: str,
    source_namespace: str,
) -> Path:
        name = _clean_string(entity.get("name"))
        entity_type = normalize_entity_type(entity.get("entity_type"))
        summary = _clean_string(entity.get("summary"))
        evidence = _clean_string(entity.get("evidence"))

        aliases = [
            _clean_string(alias)
            for alias in _as_list(entity.get("aliases"))
            if _clean_string(alias)
        ]

        value = _clean_string(entity.get("value"))
        unit = _clean_string(entity.get("unit"))
        page = _clean_string(entity.get("page"))
        confidence = _clean_string(entity.get("confidence"))
        notes = _clean_string(entity.get("notes"))

        uid = entity_uid(
            source_namespace=source_namespace,
            entity_type=entity_type,
            name=name,
        )

        path = self.entity_page_path(
            name=name,
            entity_type=entity_type,
            source_namespace=source_namespace,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        if aliases:
            aliases_yaml = "\n".join(f"  - {yaml_string(alias)}" for alias in aliases)
            aliases_frontmatter = f"aliases:\n{aliases_yaml}"
        else:
            aliases_frontmatter = "aliases: []"

        source_bullet = f"- {source_link}"

        if evidence:
            source_bullet += f" — {evidence}"

        alias_body = _markdown_bullets(
            [f"`{alias}`" for alias in aliases],
            default="- No aliases identified.",
        )

        attribute_lines: list[str] = []

        if value:
            attribute_lines.append(f"- Value: `{value}`")

        if unit:
            attribute_lines.append(f"- Unit: `{unit}`")

        if page:
            attribute_lines.append(f"- Page/location: `{page}`")

        if confidence:
            attribute_lines.append(f"- Confidence: `{confidence}`")

        if notes:
            attribute_lines.append(f"- Notes: {notes}")

        attributes_body = "\n".join(attribute_lines) if attribute_lines else "- No structured attributes identified."

        if not path.exists():
            text = f"""---
                    uid: {yaml_string(uid)}
                    title: {yaml_string(name)}
                    kind: entity
                    entity_type: {yaml_string(entity_type)}
                    source_namespace: {yaml_string(source_namespace)}
                    created_utc: {yaml_string(utc_today())}
                    {aliases_frontmatter}
                    tags:
                    - entity
                    - {slugify(entity_type, fallback="other")}
                    ---

                    # {name}

                    ## Summary

                    {summary or "_No summary available yet._"}

                    ## Entity type

                    `{entity_type}`

                    ## Aliases

                    {alias_body}

                    ## Structured attributes

                    {attributes_body}

                    ## Source grounding

                    {source_bullet}

                    ## Related concepts

                    - TBD

                    ## Related entities

                    - TBD

                    ## User notes

                    User-maintained notes about this entity can go here.
                    """
        else:
            text = path.read_text(encoding="utf-8", errors="replace")

            text = ensure_source_grounding_bullet(
                page_text=text,
                source_link=source_link,
                evidence=evidence,
            )

            if "_No summary available yet._" in text and summary:
                text = text.replace("_No summary available yet._", summary, 1)

        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path

    def upsert_concept_page(
        self,
        *,
        concept: dict[str, Any],
        source_link: str,
        source_namespace: str,
    ) -> Path:
        name = _clean_string(concept.get("name"))
        summary = _clean_string(concept.get("summary"))
        evidence = _clean_string(concept.get("evidence"))

        path = self.concept_page_path(
            name=name,
            source_namespace=source_namespace,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            text = f"""---
title: {yaml_string(name)}
kind: concept
source_namespace: {yaml_string(source_namespace)}
created_utc: {yaml_string(utc_today())}
tags:
  - concept
---

# {name}

## Summary

{summary or "_No summary available yet._"}

## Source grounding

- {source_link}

## Related concepts

- TBD

## Related entities

- TBD
"""
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            text = ensure_source_grounding_bullet(
                page_text=text,
                source_link=source_link,
                evidence=evidence,
            )

            if "_No summary available yet._" in text and summary:
                text = text.replace("_No summary available yet._", summary, 1)

        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path

    def upsert_notes_page(
        self,
        *,
        source_link: str,
        source_namespace: str,
        source_summary: str,
    ) -> Path:
        """
        Create or update a user-maintained notes page.

        Important behavior:
        - If the notes page does not exist, create it with a starter template.
        - If the notes page already exists, do not overwrite user notes.
        - On existing pages, only ensure the source grounding link is present.
        """
        path = self.notes_page_path(source_namespace=source_namespace)
        path.parent.mkdir(parents=True, exist_ok=True)

        title = f"Notes for {source_namespace}"

        if not path.exists():
            text = f"""---
title: {yaml_string(title)}
kind: notes
source_namespace: {yaml_string(source_namespace)}
created_utc: {yaml_string(utc_today())}
tags:
  - notes
  - user-maintained
---

# {title}

## User notes

Write source-specific notes here.

## Source summary at creation time

{source_summary or "_No source summary was available when this notes page was created._"}

## Source grounding

- {source_link}
"""
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
            return path

        text = path.read_text(encoding="utf-8", errors="replace")

        text = ensure_source_grounding_bullet(
            page_text=text,
            source_link=source_link,
            evidence="",
        )

        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path
    
    def upsert_document_concepts_page(
    self,
    *,
    source_link: str,
    source_namespace: str,
    concepts: list[dict[str, Any]],
) -> Path:
        path = self.document_concepts_page_path(
            source_namespace=source_namespace,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        title = f"Concepts for {source_namespace}"
        uid = page_uid(kind="document_concepts", source_namespace=source_namespace)

        concepts_body = self._render_concepts_document_body(
            source_namespace=source_namespace,
            concepts=concepts,
        )

        if not path.exists():
            text = f"""---
    uid: {yaml_string(uid)}
    title: {yaml_string(title)}
    kind: document_concepts
    source_namespace: {yaml_string(source_namespace)}
    created_utc: {yaml_string(utc_today())}
    tags:
    - concepts
    - document-concepts
    ---

    # {title}

    ## Overview

    This page contains all concepts extracted for one source document.

    ## Concepts

    {concepts_body}

    ## Source grounding

    - {source_link}

    ## User notes

    User-maintained notes about these concepts can go here.
    """
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
            return path

        text = path.read_text(encoding="utf-8", errors="replace")

        text = replace_markdown_section(
            text,
            "Overview",
            "This page contains all concepts extracted for one source document.",
        )

        text = replace_markdown_section(
            text,
            "Concepts",
            concepts_body,
        )

        text = ensure_source_grounding_bullet(
            page_text=text,
            source_link=source_link,
            evidence="",
        )

        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path
    
    def upsert_document_entities_page(
    self,
    *,
    source_link: str,
    source_namespace: str,
    entities: list[dict[str, Any]],
) -> Path:
        path = self.document_entities_page_path(
            source_namespace=source_namespace,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        title = f"Entities for {source_namespace}"
        uid = page_uid(kind="document_entities", source_namespace=source_namespace)

        entities_body = self._render_entities_document_body(
            source_namespace=source_namespace,
            entities=entities,
        )

        if not path.exists():
            text = f"""---
    uid: {yaml_string(uid)}
    title: {yaml_string(title)}
    kind: document_entities
    source_namespace: {yaml_string(source_namespace)}
    created_utc: {yaml_string(utc_today())}
    tags:
    - entities
    - document-entities
    ---

    # {title}

    ## Overview

    This page contains all entities extracted for one source document, grouped by entity type.

    ## Entities

    {entities_body}

    ## Source grounding

    - {source_link}

    ## User notes

    User-maintained notes about these entities can go here.
    """
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
            return path

        text = path.read_text(encoding="utf-8", errors="replace")

        text = replace_markdown_section(
            text,
            "Overview",
            "This page contains all entities extracted for one source document, grouped by entity type.",
        )

        text = replace_markdown_section(
            text,
            "Entities",
            entities_body,
        )

        text = ensure_source_grounding_bullet(
            page_text=text,
            source_link=source_link,
            evidence="",
        )

        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return path

    def apply_integration_data(
        self,
        *,
        source_page: Path,
        source_link: str,
        source_namespace: str,
        data: dict[str, Any],
    ) -> dict:
        source_summary = _clean_string(data.get("source_summary"))

        key_claims = [
            _clean_string(x)
            for x in _as_list(data.get("key_claims"))
            if _clean_string(x)
        ]

        caveats = [
            _clean_string(x)
            for x in _as_list(data.get("caveats"))
            if _clean_string(x)
        ]

        # entities = [
        #     x for x in _as_list(data.get("entities"))
        #     if isinstance(x, dict) and _clean_string(x.get("name"))
        # ]
        entities = [
            x for x in _as_list(data.get("entities"))
            if isinstance(x, dict) and _clean_string(x.get("name"))
        ]
        entities = normalize_and_deduplicate_entities(entities)
        entities = filter_specific_entities(entities)

        concepts = [
            x for x in _as_list(data.get("concepts"))
            if isinstance(x, dict) and _clean_string(x.get("name"))
        ]

        notes_page = self.upsert_notes_page(
            source_link=source_link,
            source_namespace=source_namespace,
            source_summary=source_summary,
        )

        entities_page = self.upsert_document_entities_page(
            source_link=source_link,
            source_namespace=source_namespace,
            entities=entities,
        )

        concepts_page = self.upsert_document_concepts_page(
            source_link=source_link,
            source_namespace=source_namespace,
            concepts=concepts,
        )

        entity_pages: list[Path] = []
        entity_page_by_uid: dict[str, Path] = {}

        for entity in entities:
            name = _clean_string(entity.get("name"))

            if not name:
                continue

            entity_type = normalize_entity_type(entity.get("entity_type"))

            entity_page = self.upsert_entity_page(
                entity=entity,
                source_link=source_link,
                source_namespace=source_namespace,
            )

            uid = entity_uid(
                source_namespace=source_namespace,
                entity_type=entity_type,
                name=name,
            )

            entity_pages.append(entity_page)
            entity_page_by_uid[uid] = entity_page

        self.update_manifest(
            source_namespace=source_namespace,
            source_page=source_page,
            source_link=source_link,
            entities_page=entities_page,
            concepts_page=concepts_page,
            notes_page=notes_page,
            entities=entities,
            concepts=concepts,
            entity_page_by_uid=entity_page_by_uid,
        )

        notes_link = wiki_link_for_path(
            self.wiki.wiki_root,
            notes_page,
        )

        entities_link = wiki_link_for_path(
            self.wiki.wiki_root,
            entities_page,
        )

        entity_link_by_uid = {
            uid: wiki_link_for_path(self.wiki.wiki_root, path)
            for uid, path in entity_page_by_uid.items()
        }

        concepts_link = wiki_link_for_path(
            self.wiki.wiki_root,
            concepts_page,
        )

        entity_summary_items: list[str] = []

        for entity in entities:
            name = _clean_string(entity.get("name"))
            entity_type = _clean_string(entity.get("entity_type")) or "other"

            if name:
                uid = entity_uid(
                    source_namespace=source_namespace,
                    entity_type=entity_type,
                    name=name,
                )
                entity_link = entity_link_by_uid.get(uid, entities_link)
                entity_summary_items.append(
                    f"`{name}` ({entity_type}, `{uid}`) — see {entity_link}"
                )

        concept_summary_items: list[str] = []

        for concept in concepts:
            name = _clean_string(concept.get("name"))

            if name:
                uid = concept_uid(
                    source_namespace=source_namespace,
                    name=name,
                )

                concept_summary_items.append(
                    f"`{name}` (`{uid}`) — see {concepts_link}"
                )

        source_text = source_page.read_text(encoding="utf-8", errors="replace")

        source_text = replace_markdown_section(
            source_text,
            "LLM-maintained summary",
            source_summary or "_No summary generated._",
        )

        source_text = replace_markdown_section(
            source_text,
            "Key claims and facts",
            _markdown_bullets(key_claims),
        )

        source_text = replace_markdown_section(
            source_text,
            "Entities to update",
            _markdown_bullets(
                entity_summary_items,
                default=f"- See {entities_link}",
            ),
        )

        source_text = replace_markdown_section(
            source_text,
            "Concepts to update",
            _markdown_bullets(
                concept_summary_items,
                default=f"- See {concepts_link}",
            ),
        )

        related_links = [
            entities_link,
            concepts_link,
            notes_link,
            "[[concept_manifest.md]]",
        ]

        source_text = replace_markdown_section(
            source_text,
            "Related wiki pages",
            _markdown_bullets(related_links),
        )

        source_text = replace_markdown_section(
            source_text,
            "Notes",
            f"- {notes_link}",
        )

        source_text = replace_markdown_section(
            source_text,
            "Contradictions, caveats, and uncertainty",
            _markdown_bullets(
                caveats,
                default="- No caveats identified by auto-integration.",
            ),
        )

        source_page.write_text(source_text.rstrip() + "\n", encoding="utf-8")

        return {
            "source_page": str(source_page),
            "source_namespace": source_namespace,
            "entities_page": str(entities_page),
            "concepts_page": str(concepts_page),
            "notes_page": str(notes_page),
            "manifest": str(self.wiki.wiki_root / "manifest.json"),
            "concept_manifest": str(self.wiki.wiki_root / "concept_manifest.md"),

            # Backward compatibility.
            # "entity_pages": [str(entities_page)],
            # "concept_pages": [str(concepts_page)],
            "document_entities_page": str(entities_page),
            "document_concepts_page": str(concepts_page),

            "entity_pages": [str(path) for path in entity_pages],
            "concept_pages": [str(concepts_page)],

            "entity_page_count": len(entity_pages),

            "entity_count": len(entities),
            "concept_count": len(concepts),
            "key_claim_count": len(key_claims),
            "caveat_count": len(caveats),
            "error": None,
        }

    def update_manifest(
        self,
        *,
        source_namespace: str,
        source_page: Path,
        source_link: str,
        entities_page: Path,
        concepts_page: Path,
        notes_page: Path,
        entities: list[dict[str, Any]],
        concepts: list[dict[str, Any]],
        entity_page_by_uid: dict[str, Path] | None = None,
    ) -> None:
        """
        Update wiki/manifest.json and wiki/concept_manifest.md.

        The manifest lets you search by concept/entity and find which source
        document it came from.
        """
        manifest_path = self.wiki.wiki_root / "manifest.json"
        concept_manifest_path = self.wiki.wiki_root / "concept_manifest.md"

        source_rel = source_page.relative_to(self.wiki.wiki_root).as_posix()
        entities_rel = entities_page.relative_to(self.wiki.wiki_root).as_posix()
        concepts_rel = concepts_page.relative_to(self.wiki.wiki_root).as_posix()
        notes_rel = notes_page.relative_to(self.wiki.wiki_root).as_posix()
        entity_page_by_uid = entity_page_by_uid or {}

        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        else:
            manifest = {}

        manifest.setdefault("sources", [])
        manifest.setdefault("entities", [])
        manifest.setdefault("concepts", [])

        # Remove old records for this source namespace so reruns refresh cleanly.
        manifest["sources"] = [
            item for item in manifest["sources"]
            if item.get("source_namespace") != source_namespace
        ]

        manifest["entities"] = [
            item for item in manifest["entities"]
            if item.get("source_namespace") != source_namespace
        ]

        manifest["concepts"] = [
            item for item in manifest["concepts"]
            if item.get("source_namespace") != source_namespace
        ]

        manifest["sources"].append(
            {
                "uid": page_uid(kind="source", source_namespace=source_namespace),
                "source_namespace": source_namespace,
                "source_page": source_rel,
                "source_link": source_link,
                "entities_page": entities_rel,
                "concepts_page": concepts_rel,
                "notes_page": notes_rel,
            }
        )

        for entity in entities:
            name = _clean_string(entity.get("name"))

            if not name:
                continue

            entity_type = normalize_entity_type(entity.get("entity_type"))
            evidence = _clean_string(entity.get("evidence"))
            summary = _clean_string(entity.get("summary"))

            uid = entity_uid(
                source_namespace=source_namespace,
                entity_type=entity_type,
                name=name,
            )

            entity_page = entity_page_by_uid.get(uid)
            entity_page_rel = (
                entity_page.relative_to(self.wiki.wiki_root).as_posix()
                if entity_page is not None
                else ""
            )

            manifest["entities"].append(
                {
                    "uid": uid,
                    "name": name,
                    "entity_type": entity_type,
                    "summary": summary,
                    "evidence": evidence,
                    "source_namespace": source_namespace,
                    "source_page": source_rel,
                    "entities_page": entities_rel,
                    "entity_page": entity_page_rel,
                    "aliases": [
                        _clean_string(alias)
                        for alias in _as_list(entity.get("aliases"))
                        if _clean_string(alias)
                    ],
                    "page": _clean_string(entity.get("page")),
                    "confidence": _clean_string(entity.get("confidence")),
                    "value": _clean_string(entity.get("value")),
                    "unit": _clean_string(entity.get("unit")),
                    "notes": _clean_string(entity.get("notes")),
                }
            )

        for concept in concepts:
            name = _clean_string(concept.get("name"))

            if not name:
                continue

            evidence = _clean_string(concept.get("evidence"))
            summary = _clean_string(concept.get("summary"))

            manifest["concepts"].append(
                {
                    "uid": concept_uid(
                        source_namespace=source_namespace,
                        name=name,
                    ),
                    "name": name,
                    "summary": summary,
                    "evidence": evidence,
                    "source_namespace": source_namespace,
                    "source_page": source_rel,
                    "concepts_page": concepts_rel,
                }
            )

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self.write_concept_manifest_md(
            concept_manifest_path=concept_manifest_path,
            manifest=manifest,
    )

    def write_concept_manifest_md(
        self,
        *,
        concept_manifest_path: Path,
        manifest: dict[str, Any],
    ) -> None:
        concepts = manifest.get("concepts") or []

        lines: list[str] = [
            "# Concept Manifest",
            "",
            "This page lists extracted concepts and the source documents where they were found.",
            "",
            "| Concept | UID | Source | Concepts page |",
            "|---|---|---|---|",
        ]

        for item in sorted(
            concepts,
            key=lambda x: (
                str(x.get("name") or "").lower(),
                str(x.get("source_namespace") or "").lower(),
            ),
        ):
            name = item.get("name") or ""
            uid = item.get("uid") or ""
            source_page = item.get("source_page") or ""
            concepts_page = item.get("concepts_page") or ""

            lines.append(
                f"| {name} | `{uid}` | [[{source_page}]] | [[{concepts_page}]] |"
            )

        lines.append("")

        concept_manifest_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def update_related_sections(
        self,
        *,
        entity_pages: list[Path],
        concept_pages: list[Path],
    ) -> None:
        entity_links = [
            wiki_link_for_path(self.wiki.wiki_root, path)
            for path in entity_pages
        ]

        concept_links = [
            wiki_link_for_path(self.wiki.wiki_root, path)
            for path in concept_pages
        ]

        for concept_page in concept_pages:
            other_concept_links = [
                wiki_link_for_path(self.wiki.wiki_root, path)
                for path in concept_pages
                if path != concept_page
            ]

            text = concept_page.read_text(encoding="utf-8", errors="replace")

            text = replace_markdown_section(
                text,
                "Related concepts",
                _markdown_bullets(
                    other_concept_links,
                    default="- No related concepts identified from this source.",
                ),
            )

            text = replace_markdown_section(
                text,
                "Related entities",
                _markdown_bullets(
                    entity_links,
                    default="- No related entities identified from this source.",
                ),
            )

            concept_page.write_text(text.rstrip() + "\n", encoding="utf-8")

        for entity_page in entity_pages:
            other_entity_links = [
                wiki_link_for_path(self.wiki.wiki_root, path)
                for path in entity_pages
                if path != entity_page
            ]

            text = entity_page.read_text(encoding="utf-8", errors="replace")

            text = replace_markdown_section(
                text,
                "Related concepts",
                _markdown_bullets(
                    concept_links,
                    default="- No related concepts identified from this source.",
                ),
            )

            text = replace_markdown_section(
                text,
                "Related entities",
                _markdown_bullets(
                    other_entity_links,
                    default="- No related entities identified from this source.",
                ),
            )

            entity_page.write_text(text.rstrip() + "\n", encoding="utf-8")