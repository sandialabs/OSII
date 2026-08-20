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


def candidate_block(
    text: str,
    *,
    top_k: int = 60,
    max_chars: int = 30000,
    document_frequency: dict[str, int] | None = None,
    corpus_size: int = 0,
) -> tuple[str, list[dict]]:
    """
    Render entity, abbreviation, and concept candidates as one prompt block.

    Three signals, because each sees something the others cannot: capitalized
    runs find named things, author-defined abbreviations supply reliable
    aliases, and noun phrases find the lowercase terms that make up concepts.
    """
    candidates = candidate_names(text, top_k=top_k)

    if document_frequency:
        candidates = rank_by_distinctiveness(candidates, document_frequency, corpus_size)

    lines: list[str] = []
    used: list[dict] = []
    size = 0

    for candidate in candidates:
        snippets = evidence_snippets(text, candidate["name"])
        if not snippets:
            continue

        entry = [f'- CANDIDATE: {candidate["name"]}']
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
        block += "\n\nABBREVIATIONS DEFINED IN THE DOCUMENT (use as aliases):\n"
        block += "\n".join(
            f'- {item["acronym"]} = {item["name"]}' for item in abbreviations[:20]
        )

    concepts = concept_candidates(text)
    if document_frequency:
        concepts = rank_by_distinctiveness(concepts, document_frequency, corpus_size)

    if concepts:
        block += "\n\nCANDIDATE CONCEPTS (frequent phrases from the full document):\n"
        block += "\n".join(f'- {item["name"]}' for item in concepts[:20])

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
