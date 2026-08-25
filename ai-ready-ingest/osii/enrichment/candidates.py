"""
Local candidate extraction over a document's full text.

Model-backed extraction reads only what fits in a prompt, which for a long
document is a small fraction of it. This module scans the whole text without a
model and produces candidates plus grounding snippets, so the model's job
becomes judging a shortlist rather than discovering entities from an excerpt.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from osii.enrichment.linguistic_examples import (
    ENTITY_HEADER_WORDS,
    ENTITY_NOISE_WORDS,
    ENTITY_RE,
    ENTITY_STARTER_WORDS,
    SENTENCE_RE,
    WORD_RE,
    _entity_type,
    _noun_or_adjective,
)

# "Write-Ahead Log (WAL)" — a definition the author wrote, giving both a
# canonical name and its abbreviation at high precision.
ACRONYM_DEFINITION_RE = re.compile(
    r"\b((?:[A-Z][\w'-]*)(?:[ -](?:[A-Za-z][\w'-]*)){0,5})\s*\(([A-Z][A-Z0-9]{1,7})s?\)"
)
LOWERCASE_TECH_RE = re.compile(
    r"\b[a-z][a-z0-9]{2,}(?:[-_.:/][a-z0-9][a-z0-9_.:/-]*)+\b"
)

VERSIONED_NAME_RE = re.compile(
    r"\b[a-zA-Z][a-zA-Z0-9_.-]*\s+v?\d+(?:\.\d+){1,4}\b"
)

FILE_OR_PATH_RE = re.compile(
    r"\b[\w.-]+\.(?:txt|toml|json|yaml|yml|csv|tsv|h5|hdf5|nc|py|js|ts|java|c|cc|cpp|h|hpp|md|pdf|docx|pptx)\b"
)

LABELED_REFERENCE_RE = re.compile(
    r"\b(?:figure|fig\.?|table|appendix|section|sec\.?|requirement|req\.?|run|case|sample|specimen|test|experiment|model|dataset)\s+[A-Za-z0-9_.:#/-]+\b",
    flags=re.IGNORECASE,
)

CODE_LITERAL_RE = re.compile(
    r"`([^`\n]{2,80})`"
)

GENERIC_LOWERCASE_CANDIDATES = {
    "model",
    "models",
    "data",
    "dataset",
    "datasets",
    "database",
    "databases",
    "software",
    "system",
    "systems",
    "component",
    "components",
    "method",
    "methods",
    "process",
    "processes",
    "approach",
    "analysis",
    "result",
    "results",
    "discussion",
    "conclusion",
    "introduction",
    "background",
    "experiment",
    "experiments",
    "simulation",
    "simulations",
    "test",
    "tests",
    "document",
    "documents",
    "report",
    "reports",
    "figure",
    "table",
    "section",
}


def _clean_candidate(raw: str) -> str:
    """Trim leading sentence-starter words the regex sweeps up."""
    words = " ".join(raw.split()).strip(" .").split()

    drop = 0
    while drop < len(words) and (
        words[drop] in ENTITY_STARTER_WORDS
        or (drop > 0 and words[drop].casefold() == "the")
    ):
        drop += 1

    return " ".join(words[drop:])


def _is_noise(name: str) -> bool:
    words = name.split()

    if not words:
        return True

    if len(words) == 1:
        single = words[0]
        if single in ENTITY_STARTER_WORDS or single.casefold() in ENTITY_NOISE_WORDS:
            return True
        if len(single) < 3 and not single.isupper():
            return True

    if len(words) > 1 and all(
        word.casefold().strip(".:") in ENTITY_HEADER_WORDS for word in words
    ):
        return True

    return False


def candidate_names(text: str, *, top_k: int = 60, min_count: int = 2) -> list[dict]:
    """
    Frequent capitalized names and acronyms across the whole text.

    Ranked by occurrence count so the shortlist favours terms the document
    actually dwells on.
    """
    counts: Counter[str] = Counter()

    for match in ENTITY_RE.finditer(text):
        name = _clean_candidate(match.group(0))
        if name and not _is_noise(name):
            counts[name] += 1

    return [
        {"name": name, "count": count, "candidate_type": _entity_type(name)}
        for name, count in counts.most_common(top_k)
        if count >= min_count
    ]


def evidence_snippets(
    text: str,
    name: str,
    *,
    max_snippets: int = 3,
    window: int = 180,
) -> list[str]:
    """
    Short windows around a candidate, spread across the document.

    Occurrences are sampled at intervals rather than taken from the front, so a
    term introduced in the preface is not judged only on its preface mentions.
    """
    positions: list[int] = []
    start = 0

    while len(positions) < 400:
        found = text.find(name, start)
        if found == -1:
            break
        positions.append(found)
        start = found + len(name)

    if not positions:
        return []

    step = max(1, len(positions) // max_snippets)
    chosen = positions[::step][:max_snippets]

    snippets = []
    for position in chosen:
        left = max(0, position - window // 2)
        right = min(len(text), position + len(name) + window // 2)
        snippet = " ".join(text[left:right].split())
        snippets.append(snippet)

    return snippets

def merge_candidate_lists(*candidate_lists: list[dict]) -> list[dict]:
    """
    Merge candidates by normalized lowercase name while preserving counts and source types.
    """
    merged: dict[str, dict] = {}

    for candidate_list in candidate_lists:
        for candidate in candidate_list:
            name = " ".join(str(candidate.get("name") or "").split()).strip()
            if not name:
                continue

            key = name.lower()

            if key not in merged:
                merged[key] = {
                    **candidate,
                    "name": name,
                    "count": int(candidate.get("count") or 1),
                    "candidate_types": [candidate.get("candidate_type") or "candidate"],
                }
            else:
                merged[key]["count"] += int(candidate.get("count") or 1)
                ctype = candidate.get("candidate_type") or "candidate"
                if ctype not in merged[key]["candidate_types"]:
                    merged[key]["candidate_types"].append(ctype)

    return list(merged.values())

def candidate_quality_score(candidate: dict) -> float:
    name = str(candidate.get("name") or "").strip()
    count = int(candidate.get("count") or 1)
    candidate_types = candidate.get("candidate_types") or [candidate.get("candidate_type")]

    score = float(count)

    # Acronyms and proper names are useful.
    if re.search(r"\b[A-Z]{2,}\b", name):
        score += 4.0

    # IDs, versions, figures, tables, files, paths, and run names are useful.
    if re.search(r"\d", name):
        score += 3.0

    if re.search(r"[-_./:#]", name):
        score += 3.0

    # Multi-word title-case names are usually good.
    words = name.split()
    if len(words) >= 2 and any(word[:1].isupper() for word in words):
        score += 2.0

    # Code literals and lowercase technical names are strong.
    if "lowercase_specific_candidate" in candidate_types:
        score += 3.0

    # Penalize generic section-ish words.
    if name.lower() in ENTITY_NOISE_WORDS:
        score -= 5.0

    if name.lower() in ENTITY_HEADER_WORDS:
        score -= 5.0

    return score

def candidate_block(
    text: str,
    *,
    top_k: int = 60,
    max_chars: int = 30000,
    document_frequency: dict[str, int] | None = None,
    corpus_size: int = 0,
) -> tuple[str, list[dict]]:
    """
    Render entity, abbreviation, lowercase technical, and concept candidates
    as one prompt block.
    """
    capitalized = candidate_names(
        text,
        top_k=top_k * 4,
        min_count=2,
    )

    lowercase_specific = lowercase_specific_candidates(
        text,
        top_k=top_k * 4,
        min_count=1,
    )

    candidates = merge_candidate_lists(capitalized, lowercase_specific)

    if document_frequency:
        candidates = rank_by_distinctiveness(
            candidates,
            document_frequency,
            corpus_size,
        )

    candidates = sorted(
        candidates,
        key=lambda item: -candidate_quality_score(item),
    )

    lines: list[str] = []
    used: list[dict] = []
    size = 0

    for candidate in candidates:
        if len(used) >= top_k:
            break

        snippets = evidence_snippets(text, candidate["name"])
        if not snippets:
            continue

        ctype = candidate.get("candidate_type") or ",".join(candidate.get("candidate_types") or [])

        entry = [
            f'- CANDIDATE: {candidate["name"]}',
            f'  CANDIDATE_TYPE: {ctype}',
            f'  COUNT: {candidate.get("count", "")}',
        ]
        entry.extend(f"  EVIDENCE: {snippet}" for snippet in snippets)

        rendered = "\n".join(entry)

        if size + len(rendered) > max_chars:
            break

        lines.append(rendered)
        used.append(candidate)
        size += len(rendered)

    block = "\n".join(lines)

    abbreviations = acronym_definitions(text)
    if abbreviations:
        abbrev_lines = [
            "",
            "ABBREVIATIONS DEFINED IN THE DOCUMENT (use as aliases):",
            *[
                f'- {item["acronym"]} = {item["name"]}'
                for item in abbreviations[:20]
            ],
        ]

        rendered = "\n".join(abbrev_lines)
        if size + len(rendered) <= max_chars:
            block += "\n" + rendered
            size += len(rendered)

    concepts = concept_candidates(text)

    if document_frequency:
        concepts = rank_by_distinctiveness(concepts, document_frequency, corpus_size)

    if concepts:
        concept_lines = [
            "",
            "CANDIDATE CONCEPTS (frequent phrases from the full document):",
            *[f'- {item["name"]}' for item in concepts[:20]],
        ]

        rendered = "\n".join(concept_lines)
        if size + len(rendered) <= max_chars:
            block += "\n" + rendered

    return block, used

def acronym_definitions(text: str, *, max_items: int = 40) -> list[dict]:
    """
    Names paired with the abbreviation the document defines for them.

    These are the most reliable aliases available: the author stated them, so
    they need no inference and rarely need rejecting.
    """
    found: dict[str, str] = {}

    for match in ACRONYM_DEFINITION_RE.finditer(text):
        name = " ".join(match.group(1).split()).strip(" -")
        acronym = match.group(2)

        if len(name) < 3 or name.upper() == acronym:
            continue

        tightened = _tighten_to_acronym(name, acronym)
        if not tightened:
            continue

        found.setdefault(tightened, acronym)

        if len(found) >= max_items:
            break

    return [{"name": name, "acronym": acronym} for name, acronym in found.items()]


def concept_candidates(text: str, *, top_k: int = 25, min_count: int = 3) -> list[dict]:
    """
    Frequent lowercase noun and adjective phrases.

    Entity candidates only ever match capitalized runs, so multi-word terms
    like "primary key" or "load balancer" are invisible to them. These are what
    concepts are usually made of.
    """
    counts: Counter[tuple[str, ...]] = Counter()

    for sentence in SENTENCE_RE.findall(text):
        run: list[str] = []
        runs: list[list[str]] = []

        for token in WORD_RE.findall(sentence):
            tagged = _noun_or_adjective(token)
            if tagged is None:
                if run:
                    runs.append(run)
                    run = []
                continue
            run.append(tagged[0])

        if run:
            runs.append(run)

        for lemmas in runs:
            for width in (2, 3):
                for offset in range(len(lemmas) - width + 1):
                    counts[tuple(lemmas[offset:offset + width])] += 1

    return [
        {"name": " ".join(ngram), "count": count}
        for ngram, count in counts.most_common(top_k * 4)
        if count >= min_count
    ][:top_k]


def rank_by_distinctiveness(
    candidates: list[dict],
    document_frequency: dict[str, int],
    corpus_size: int,
) -> list[dict]:
    """
    Reorder candidates by tf-idf rather than raw count.

    Raw frequency favours vocabulary the whole corpus shares, so a term central
    to one document loses to boilerplate that appears everywhere.
    """
    if corpus_size <= 1 or not document_frequency:
        return candidates

    scored = []
    for candidate in candidates:
        df = max(1, document_frequency.get(candidate["name"].lower(), 1))
        idf = math.log(1 + corpus_size / df)
        scored.append(({**candidate, "score": candidate["count"] * idf}, candidate["count"] * idf))

    scored.sort(key=lambda pair: -pair[1])
    return [item for item, _ in scored]


def _tighten_to_acronym(name: str, acronym: str) -> str | None:
    """
    Trim a captured name to the words the acronym actually stands for.

    The pattern sweeps up whatever precedes the parenthesis, so "Download the
    Java Database Connectivity (JDBC)" has to be reduced to the three words
    whose initials spell JDBC.
    """
    words = name.split()
    best: str | None = None

    for start in range(len(words)):
        tail = words[start:]
        initials = "".join(word[0].upper() for word in tail if word[:1].isupper())
        if initials == acronym:
            best = " ".join(tail)

    return best


def load_or_build_document_frequency(osii_root: Path, file_ids: list[str]) -> tuple[dict[str, int], int]:
    """
    How many documents each candidate term appears in, cached on disk.

    Distinctiveness needs a corpus view, but rebuilding it means reading every
    document. The cache is keyed by the set of documents, so it is rebuilt only
    when the corpus changes rather than on every run.
    """
    ordered = sorted(file_ids)
    if len(ordered) < 2:
        return {}, len(ordered)

    key = hashlib.sha1("::".join(ordered).encode("utf-8")).hexdigest()[:16]
    cache_path = osii_root / "enrichments" / f".candidate_df-{key}.json"

    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached["document_frequency"], int(cached["corpus_size"])
        except Exception:
            pass

    document_frequency: Counter[str] = Counter()

    for file_id in ordered:
        text_path = osii_root / "objects" / file_id / "text.txt"
        if not text_path.is_file():
            continue

        body = text_path.read_text(encoding="utf-8", errors="replace")
        terms = {item["name"].lower() for item in candidate_names(body, top_k=400)}
        terms |= {item["name"].lower() for item in concept_candidates(body, top_k=200)}

        for term in terms:
            document_frequency[term] += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"corpus_size": len(ordered), "document_frequency": dict(document_frequency)}),
        encoding="utf-8",
    )

    return dict(document_frequency), len(ordered)

def lowercase_specific_candidates(
    text: str,
    *,
    top_k: int = 60,
    min_count: int = 1,
) -> list[dict]:
    """
    Find lowercase/code-like specific entities that capitalized-name extraction misses.

    This intentionally favors things with identifiers, punctuation, versions,
    file extensions, code formatting, or labeled references.
    """
    counts: Counter[str] = Counter()

    regexes = [
        LOWERCASE_TECH_RE,
        VERSIONED_NAME_RE,
        FILE_OR_PATH_RE,
        LABELED_REFERENCE_RE,
    ]

    for regex in regexes:
        for match in regex.finditer(text):
            name = " ".join(match.group(0).split()).strip(" .,:;()[]{}")
            if _is_bad_lowercase_candidate(name):
                continue
            counts[name] += 1

    for match in CODE_LITERAL_RE.finditer(text):
        name = " ".join(match.group(1).split()).strip(" .,:;()[]{}")
        if _is_bad_lowercase_candidate(name):
            continue
        if _looks_like_code_entity(name):
            counts[name] += 2  # code formatting is strong evidence

    ranked = sorted(
        counts.items(),
        key=lambda pair: (-_lowercase_specificity_score(pair[0], pair[1]), pair[0].lower()),
    )

    return [
        {
            "name": name,
            "count": count,
            "candidate_type": "lowercase_specific_candidate",
        }
        for name, count in ranked[:top_k]
        if count >= min_count
    ]


def _is_bad_lowercase_candidate(name: str) -> bool:
    value = " ".join(str(name or "").split()).strip().lower()

    if not value:
        return True

    if value in GENERIC_LOWERCASE_CANDIDATES:
        return True

    if len(value) < 3:
        return True

    # Reject plain lowercase prose words unless they have some identifying feature.
    if re.fullmatch(r"[a-z]+", value) and value not in _KNOWN_LOWERCASE_TECH_NAMES:
        return True

    return False


_KNOWN_LOWERCASE_TECH_NAMES = {
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "matplotlib",
    "seaborn",
    "xarray",
    "dask",
    "sqlite",
    "postgres",
    "postgresql",
    "mysql",
    "redis",
    "hdf5",
    "netcdf",
    "yaml",
    "json",
    "toml",
    "python",
    "pytest",
    "ollama",
}


def _looks_like_code_entity(name: str) -> bool:
    value = str(name or "").strip()

    if not value:
        return False

    if value.lower() in GENERIC_LOWERCASE_CANDIDATES:
        return False

    if value.lower() in _KNOWN_LOWERCASE_TECH_NAMES:
        return True

    if re.search(r"\d", value):
        return True

    if re.search(r"[-_./:#]", value):
        return True

    if re.search(r"\.(txt|toml|json|yaml|yml|csv|tsv|h5|hdf5|nc|py|md)$", value, re.I):
        return True

    return False


def _lowercase_specificity_score(name: str, count: int) -> float:
    score = float(count)

    if re.search(r"\d", name):
        score += 3.0

    if re.search(r"[-_./:#]", name):
        score += 3.0

    if re.search(r"\.(txt|toml|json|yaml|yml|csv|tsv|h5|hdf5|nc|py|md)$", name, re.I):
        score += 4.0

    if name.lower() in _KNOWN_LOWERCASE_TECH_NAMES:
        score += 4.0

    if len(name) >= 8:
        score += 1.0

    return score