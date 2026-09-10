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
from dataclasses import dataclass
from pathlib import Path

from osii.enrichment.linguistic_examples import (
    COMMON_VERBS,
    ENTITY_HEADER_WORDS,
    ENTITY_NOISE_WORDS,
    ENTITY_RE,
    ENTITY_STARTER_WORDS,
    FUNCTION_WORDS,
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


# ---------------------------------------------------------------------------
# Salience
#
# Frequency alone cannot see a term that a document mentions once and means.
# A term named in the title, a heading, a caption, or a definition is important
# on the first mention; a term appearing once in a reference list is not.
# Position and form separate them, and neither needs a model.
# ---------------------------------------------------------------------------

# How many raw candidates to consider before ranking. Selection used to cut by
# raw count and then rank, so distinctiveness could only reorder terms that had
# already won on frequency. Ranking a pool and cutting afterwards lets a rare
# term compete for a place.
CANDIDATE_POOL_FACTOR = 10

# Share of the shortlist reserved for terms the document mentions once, so a
# document that repeats its boilerplate cannot fill every slot.
RARE_QUOTA_FRACTION = 0.3

# Concepts rendered into the prompt block.
CONCEPT_BLOCK_LIMIT = 20

# Phrase widths counted for every document.
NGRAM_WIDTHS = (2, 3)

# Widths counted but admitted only on salience. A single word is too noisy to
# take on frequency, and a four-word phrase is too rare to reach a count
# threshold, so both depend on where they appear rather than how often.
LABEL_ONLY_WIDTH = 1
SALIENT_ONLY_WIDTHS = (LABEL_ONLY_WIDTH, 4)

# Words that name a document's furniture rather than its subject. A single word
# from a heading is a topic unless the heading is structural.
STRUCTURAL_WORDS = frozenset({
    "abstract", "acknowledgement", "acknowledgements", "analysis", "appendix",
    "appendices", "background", "chapter", "conclusion", "conclusions", "content",
    "contents", "data", "discussion", "document", "figure", "finding", "findings",
    "introduction", "method", "methodology", "methods", "note", "notes",
    "objective", "objectives", "overview", "page", "paper", "purpose",
    "reference", "references", "report", "result", "results", "scope", "section",
    "study", "summary", "synopsis", "table",
})

# A rescued gerund has to be long enough to be a term rather than a fragment.
GERUND_MIN_CHARS = 6

# A single word competes against phrases whose counts are far smaller, so its
# allocation is capped rather than left to the ranking.
SINGLE_WORD_LIMIT = 5


def _phrase_segments(source: str) -> list[str]:
    """
    Spans within which a noun run may form.

    Markdown table cells sit on one line separated by pipes, and a run crossing
    them joins words that were never adjacent: "osii-data source untrusted
    arbitrary" is four unrelated cells of one row.
    """
    return SENTENCE_RE.findall(source.replace("|", "\n").replace("\t", "\n"))

# Bumped when the meaning of a cached document-frequency map changes.
DF_CACHE_VERSION = "v3"

_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+)$", re.MULTILINE)

_CAPTION_RE = re.compile(
    r"^\s*((?:figure|fig\.?|table|tbl\.?|chart|plot|listing|appendix|equation|eq\.?|scheme)"
    r"\s*[0-9IVXivx][^\n]{0,200})$",
    re.IGNORECASE | re.MULTILINE,
)

# Only sections that are short and deliberate get a body window. An
# introduction or a discussion is long and discursive, so a term appearing once
# inside one is not salient by virtue of being there - and on a short document a
# window over it would make most of the text salient. Their heading text is
# still picked up as a heading like any other.
_DENSE_SECTION_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*\s*)?"
    r"(?:abstract|summary|executive\s+summary|overview|synopsis|"
    r"conclusion|conclusions|key\s+findings|findings|"
    r"scope|purpose|objective|objectives)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_DEFINITION_MARKER = (
    r"(?:is|are|was|were)\s+"
    r"(?:defined\s+as|known\s+as|referred\s+to\s+as|called|termed)"
)

# The term being defined sits before the marker, not after it. Capturing only
# what follows records what the term means and loses the term itself, which is
# the half worth shortlisting.
_DEFINED_TERM_RE = re.compile(
    rf"([^.;\n]{{0,80}})\s+{_DEFINITION_MARKER}\b",
    re.IGNORECASE,
)

_DEFINITION_RE = re.compile(
    rf"{_DEFINITION_MARKER}\s+([^.;\n]{{0,160}})"
    r"|(?:we|this\s+(?:paper|report|study|work|document|note))\s+"
    r"(?:develop|developed|present|presents|introduce|introduces|propose|proposes|"
    r"describe|describes|use|uses|used)\s+([^.;\n]{0,160})",
    re.IGNORECASE,
)

# A heading in extracted text often survives as a short line with no closing
# punctuation, having lost its markdown along the way.
_BARE_HEADING_MAX_CHARS = 80

_IDENTIFIER_FORM_RE = re.compile(r"[0-9]|[-_/.:#]")

# "3. Approach", "4.1 Masking". A numbered section survives PDF extraction even
# when every blank line around it does not.
_NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][^.!?]{0,70}$")

# Characters either side of a match, so "the RX-7 assembly" does not count as a
# mention of "X-7".
_WORD_EDGE = r"[0-9a-z]"


def _bare_heading_lines(text: str) -> list[str]:
    """
    Short standalone lines that read as headings.

    Isolation is required, not just brevity. Text extracted from a PDF is
    nothing but short lines, and without the blank line either side this
    accepts mid-paragraph fragments - "Transfer per-", "During", "Second" -
    as though the author had made them headings.
    """
    lines = []
    raw_lines = text.splitlines()

    for position, raw in enumerate(raw_lines):
        line = raw.strip()

        if not line or len(line) > _BARE_HEADING_MAX_CHARS:
            continue

        if line[-1] in ".,;:-":
            continue

        before = raw_lines[position - 1].strip() if position > 0 else ""
        after = raw_lines[position + 1].strip() if position + 1 < len(raw_lines) else ""

        if (before or after) and not _NUMBERED_HEADING_RE.match(line):
            continue

        words = line.split()

        if len(words) < 2 or len(words) > 12:
            continue

        if line.isupper() or sum(1 for word in words if word[:1].isupper()) >= len(words) - 1:
            lines.append(line)

    return lines


def _next_heading_start(text: str, position: int) -> int | None:
    """Where the section beginning at ``position`` ends, if a heading ends it."""
    for match in _MARKDOWN_HEADING_RE.finditer(text, position):
        return match.start()

    return None


def _section_bodies(text: str, *, body_chars: int = 1200) -> list[str]:
    """
    Text following a heading such as Abstract, Summary, or Conclusions.

    A window is bounded by the next heading as well as by ``body_chars``. A
    fixed-length window alone runs past the end of a short section and pulls in
    the body of whatever follows it, which on a short document is most of the
    document.
    """
    bodies = []

    for match in _DENSE_SECTION_RE.finditer(text):
        start = match.end()
        end = start + body_chars

        next_heading = _next_heading_start(text, start)

        if next_heading is not None:
            end = min(end, next_heading)

        body = text[start:end].strip()

        if body:
            bodies.append(body)

    return bodies


def salient_text(text: str, *, head_chars: int = 1500) -> str:
    """
    The regions of a document where a first mention already means something.

    Returned lowercased and concatenated, so membership can be tested with a
    plain substring check against the same normalization everywhere.
    """
    # The head window stands in for a title block and abstract. On a short
    # document it would cover the whole text and make every term salient, so
    # it is used only when there is a document left outside it.
    if len(text) > head_chars * 3:
        parts: list[str] = [text[:head_chars]]
    else:
        first_line = next((line for line in text.splitlines() if line.strip()), "")
        parts = [first_line]

    parts.extend(_MARKDOWN_HEADING_RE.findall(text))
    parts.extend(_bare_heading_lines(text))
    parts.extend(match.group(1) for match in _CAPTION_RE.finditer(text))
    parts.extend(_section_bodies(text))
    parts.extend(_DEFINED_TERM_RE.findall(text))

    for match in _DEFINITION_RE.finditer(text):
        parts.extend(group for group in match.groups() if group)

    return "\n".join(parts).lower()


def salient_labels(text: str) -> str:
    """
    The tightest salient regions: title, headings, captions, and definitions.

    A term named in one of these is being labelled, not merely used. That is a
    stronger claim than appearing somewhere in an abstract, and it is what a
    single word has to meet before it can stand as a concept on its own.
    """
    first_line = next((line for line in text.splitlines() if line.strip()), "")

    parts: list[str] = [first_line]

    parts.extend(_MARKDOWN_HEADING_RE.findall(text))
    parts.extend(_bare_heading_lines(text))
    parts.extend(match.group(1) for match in _CAPTION_RE.finditer(text))
    parts.extend(_DEFINED_TERM_RE.findall(text))

    for match in _DEFINITION_RE.finditer(text):
        parts.extend(group for group in match.groups() if group)

    return "\n".join(parts).lower()


def _verb_bases(value: str) -> set[str]:
    """Plausible stems of an -ing or -ed form, for testing against verbs."""
    bases: set[str] = set()

    if value.endswith("ing"):
        stem = value[:-3]
        bases |= {stem, stem + "e"}
    elif value.endswith("ed"):
        stem = value[:-2]
        bases |= {stem, stem + "e", value[:-1]}
    else:
        return bases

    if len(stem) > 2 and stem[-1] == stem[-2]:
        bases.add(stem[:-1])

    return bases


def _gerund_form(token: str) -> str | None:
    """
    An -ing or -ed word that could name a thing rather than an action.

    ``_noun_or_adjective`` drops every one of these to keep verb phrases out of
    the candidate set, which also drops "cladding", "annealing", and
    "ratcheting". Participles of ordinary reporting verbs are rejected here, so
    "described" and "provided" stay out while domain terms survive.
    """
    value = token.lower().strip("'-")

    if len(value) < GERUND_MIN_CHARS or not value.endswith(("ing", "ed")):
        return None

    if value in FUNCTION_WORDS or value in COMMON_VERBS:
        return None

    if _verb_bases(value) & COMMON_VERBS:
        return None

    return value


def _gerunds_in(salient_lower: str) -> frozenset[str]:
    return frozenset(
        form
        for token in WORD_RE.findall(salient_lower)
        if (form := _gerund_form(token)) is not None
    )


def _concept_token(token: str, allowed_gerunds: frozenset[str]) -> str | None:
    """The lemma a concept run is built from, or None if the run breaks here."""
    tagged = _noun_or_adjective(token)

    if tagged is not None:
        return tagged[0]

    form = _gerund_form(token)

    if form is not None and form in allowed_gerunds:
        return form

    return None


def _lemma_stream(source: str, allowed_gerunds: frozenset[str]) -> str:
    """
    ``source`` normalized the way concept names are, run by run.

    Concept names are runs of noun and adjective lemmas, so "control samples"
    in a heading becomes the candidate "control sample". Testing that candidate
    against raw text would miss, and the same normalization has to be applied
    to both sides for the comparison to mean anything.
    """
    runs: list[str] = []

    for sentence in _phrase_segments(source):
        run: list[str] = []

        for token in WORD_RE.findall(sentence):
            lemma = _concept_token(token, allowed_gerunds)

            if lemma is None:
                if run:
                    runs.append(" ".join(run))
                    run = []
                continue

            run.append(lemma)

        if run:
            runs.append(" ".join(run))

    return "\n".join(runs)


def salient_lemmas(text: str, *, head_chars: int = 1500) -> str:
    """The broad salient regions, lemmatized the way concept candidates are."""
    raw = salient_text(text, head_chars=head_chars)

    return _lemma_stream(raw, _gerunds_in(raw))


@dataclass(frozen=True)
class SalienceIndex:
    """
    Everything the admission tests need about where a document says things.

    Held together rather than passed as loose strings: a name is compared
    against raw text and a concept against lemmas, and passing one where the
    other belongs fails silently on exactly the plurals it was built for.
    """

    raw: str
    labels: str
    lemmas: str
    label_lemmas: str
    gerunds: frozenset[str]


def build_salience_index(text: str, *, head_chars: int = 1500) -> SalienceIndex:
    raw = salient_text(text, head_chars=head_chars)
    labels = salient_labels(text)
    gerunds = _gerunds_in(raw)

    return SalienceIndex(
        raw=raw,
        labels=labels,
        lemmas=_lemma_stream(raw, gerunds),
        label_lemmas=_lemma_stream(labels, gerunds),
        gerunds=gerunds,
    )


def _has_identifier_form(name: str) -> bool:
    """Names that carry an identifier's shape are specific on sight."""
    if _IDENTIFIER_FORM_RE.search(name):
        return True

    return name.isupper() and len(name) >= 3


def is_salient(name: str, salient_lower: str | None) -> bool:
    """
    Whether a term earns a place without the frequency it does not have.

    Membership is tested on word boundaries: a substring test alone would admit
    any short name that happens to sit inside a longer salient phrase.

    ``None`` means salience is switched off, and nothing is admitted by it -
    including identifier form, which is a channel of salience rather than a
    way around it.
    """
    if salient_lower is None:
        return False

    if _has_identifier_form(name):
        return True

    if not salient_lower:
        return False

    needle = re.escape(name.lower().strip())

    if not needle:
        return False

    pattern = rf"(?<!{_WORD_EDGE}){needle}(?!{_WORD_EDGE})"

    return re.search(pattern, salient_lower) is not None


def _salience_rank(name: str, salient_lower: str | None, label_lower: str | None) -> int:
    """
    How strong the claim is, for choosing between terms with no frequency.

    Single mentions all score the same under tf-idf, so without this the ones
    that survive the quota are whichever the counter happened to yield first -
    and "ResNet-50" loses its place to "During".
    """
    if salient_lower is None:
        return 0

    if _has_identifier_form(name):
        return 2

    if label_lower and is_salient(name, label_lower):
        return 1

    return 0


def _select_with_rare_quota(
    candidates: list[dict],
    *,
    top_k: int,
    quota_fraction: float = RARE_QUOTA_FRACTION,
) -> list[dict]:
    """
    Cut a ranked pool to ``top_k`` while keeping room for single-mention terms.

    Ranked order is preserved; only which candidates survive the cut changes.
    """
    if len(candidates) <= top_k:
        return candidates

    reserved = int(top_k * quota_fraction) if quota_fraction > 0 else 0
    reserved = max(0, min(reserved, top_k))

    head = candidates[: top_k - reserved]
    selected = {candidate["name"] for candidate in head}

    if reserved:
        rare = sorted(
            (c for c in candidates if c.get("count", 0) <= 1 and c["name"] not in selected),
            key=lambda c: (-c.get("salience_rank", 0), -c.get("count", 0)),
        )

        for candidate in rare:
            if len(selected) >= top_k:
                break
            selected.add(candidate["name"])

    # A document with few single-mention terms should still fill its shortlist.
    for candidate in candidates:
        if len(selected) >= top_k:
            break
        selected.add(candidate["name"])

    return [candidate for candidate in candidates if candidate["name"] in selected][:top_k]


def candidate_names(
    text: str,
    *,
    top_k: int = 60,
    min_count: int = 2,
    salience: "SalienceIndex | None" = None,
) -> list[dict]:
    """
    Capitalized names and acronyms across the whole text.

    Frequency is the usual admission test, and salience is the second one: a
    term the document mentions once is kept when it appears where a first
    mention already carries weight. Counting is done over the whole pool
    before the cut, so a term is never dropped merely for sitting below a more
    frequent one that the filter would have rejected anyway.
    """
    counts: Counter[str] = Counter()

    for match in ENTITY_RE.finditer(text):
        name = _clean_candidate(match.group(0))
        if name and not _is_noise(name):
            counts[name] += 1

    kept: list[dict] = []
    salient_lower = salience.raw if salience else None
    label_lower = salience.labels if salience else None

    for name, count in counts.most_common(max(top_k * CANDIDATE_POOL_FACTOR, top_k)):
        salient = count < min_count and is_salient(name, salient_lower)

        if count < min_count and not salient:
            continue

        kept.append({
            "name": name,
            "count": count,
            "candidate_type": _entity_type(name),
            "salient": salient,
            "salience_rank": _salience_rank(name, salient_lower, label_lower),
        })

        if len(kept) >= top_k:
            break

    return kept


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
    min_count: int = 2,
    concept_min_count: int = 3,
    rare_quota: float = RARE_QUOTA_FRACTION,
    salience: bool = True,
) -> tuple[str, list[dict]]:
    """
    Render entity, abbreviation, lowercase technical, and concept candidates
    as one prompt block.

    Five signals, because each sees something the others cannot: capitalized
    runs find named things, the lowercase scan finds technical terms that are
    never capitalized, author-defined abbreviations supply reliable aliases,
    noun phrases find the terms that make up concepts, and salience finds what
    a document says once and means.

    The ``salience`` flag turns the last one off, leaving frequency alone to
    decide. Candidates are ranked over a pool and cut afterwards: cutting first
    by raw count left distinctiveness able only to reorder terms that had
    already won on frequency, so a rare but important term could never reach
    the shortlist.
    """
    index = build_salience_index(text) if salience else None

    pool_size = max(top_k * CANDIDATE_POOL_FACTOR, top_k)

    capitalized = candidate_names(
        text,
        top_k=pool_size,
        min_count=min_count,
        salience=index,
    )

    lowercase_specific = lowercase_specific_candidates(
        text,
        top_k=pool_size,
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

    candidates = _select_with_rare_quota(
        candidates,
        top_k=top_k,
        quota_fraction=rare_quota,
    )

    # The character budget is applied with the same reservation as the shortlist
    # itself. Rendering strictly in ranked order would let a long tail of
    # frequent terms spend the whole budget, cutting the single-mention entries
    # that the quota just went to the trouble of selecting.
    rendered_by_name: dict[str, str] = {}
    size = 0

    rare_budget = int(max_chars * rare_quota) if rare_quota > 0 else 0

    def render(pool: list[dict], budget: int) -> int:
        spent = 0

        for candidate in pool:
            if candidate["name"] in rendered_by_name:
                continue

            snippets = evidence_snippets(text, candidate["name"])
            if not snippets:
                continue

            ctype = candidate.get("candidate_type") or ",".join(
                candidate.get("candidate_types") or []
            )

            entry = [
                f'- CANDIDATE: {candidate["name"]}',
                f'  CANDIDATE_TYPE: {ctype}',
                f'  COUNT: {candidate.get("count", "")}',
            ]

            # A single mention reads as noise unless the reason it was
            # shortlisted travels with it. Kept on its own labelled line so it
            # is not mistaken for part of the name.
            if candidate.get("count", 0) <= 1:
                entry.append(
                    "  SALIENCE: mentioned once; shortlisted for where it "
                    "appears, not how often"
                )

            entry.extend(f"  EVIDENCE: {snippet}" for snippet in snippets)
            text_entry = "\n".join(entry)

            if spent + len(text_entry) > budget:
                continue

            rendered_by_name[candidate["name"]] = text_entry
            spent += len(text_entry)

        return spent

    size += render(
        [c for c in candidates if c.get("count", 0) <= 1],
        rare_budget,
    )
    size += render(candidates, max_chars - size)

    # Emitted in ranked order regardless of which pass rendered them.
    used = [c for c in candidates if c["name"] in rendered_by_name]
    block = "\n".join(rendered_by_name[c["name"]] for c in used)

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

    concepts = concept_candidates(
        text,
        top_k=max(CONCEPT_BLOCK_LIMIT * CANDIDATE_POOL_FACTOR, CONCEPT_BLOCK_LIMIT),
        min_count=concept_min_count,
        salience=index,
    )

    if document_frequency:
        concepts = rank_by_distinctiveness(concepts, document_frequency, corpus_size)

    concepts = _select_with_rare_quota(
        concepts,
        top_k=CONCEPT_BLOCK_LIMIT,
        quota_fraction=rare_quota,
    )

    if concepts:
        concept_lines = [
            "",
            "CANDIDATE CONCEPTS (recurring or prominently placed phrases "
            "from the full document):",
            *[
                f'- {item["name"]}'
                + (" (mentioned once)" if item.get("count", 0) <= 1 else "")
                for item in concepts
            ],
        ]

        rendered = "\n".join(concept_lines)
        if size + len(rendered) <= max_chars:
            block += "\n" + rendered
            size += len(rendered)

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


def concept_candidates(
    text: str,
    *,
    top_k: int = 25,
    min_count: int = 3,
    salience: "SalienceIndex | None" = None,
) -> list[dict]:
    """
    Noun and adjective phrases, lowercase, one to four words wide.

    Entity candidates only ever match capitalized runs, so multi-word terms
    like "primary key" or "load balancer" are invisible to them. These are what
    concepts are usually made of, and this is the path an important topic takes.

    Two- and three-word phrases are admitted on frequency or on salience. One-
    and four-word phrases are admitted on salience alone: a single word is too
    common to earn a place by repetition, and a four-word phrase too rare to
    reach any count threshold. A single word additionally has to come from a
    heading, caption, or definition rather than from anywhere salient, and must
    not be the name of a document's furniture.
    """
    gerunds = salience.gerunds if salience else frozenset()

    counts: Counter[tuple[str, ...]] = Counter()
    salient_only: Counter[tuple[str, ...]] = Counter()

    for sentence in _phrase_segments(text):
        run: list[str] = []
        runs: list[list[str]] = []

        for token in WORD_RE.findall(sentence):
            lemma = _concept_token(token, gerunds)

            if lemma is None:
                if run:
                    runs.append(run)
                    run = []
                continue

            run.append(lemma)

        if run:
            runs.append(run)

        for lemmas in runs:
            for width in NGRAM_WIDTHS:
                for offset in range(len(lemmas) - width + 1):
                    counts[tuple(lemmas[offset:offset + width])] += 1

            for width in SALIENT_ONLY_WIDTHS:
                for offset in range(len(lemmas) - width + 1):
                    salient_only[tuple(lemmas[offset:offset + width])] += 1

    pool = max(top_k * CANDIDATE_POOL_FACTOR, top_k)
    lemma_index = salience.lemmas if salience else None
    label_index = salience.label_lemmas if salience else None

    kept: list[dict] = []

    for ngram, count in counts.most_common(pool):
        name = " ".join(ngram)
        salient = count < min_count and is_salient(name, lemma_index)

        if count < min_count and not salient:
            continue

        kept.append({"name": name, "count": count, "salient": salient})

    # Words already carried by an admitted phrase add nothing, and splitting
    # "prompt injection" into "prompt" and "injection" loses the term while
    # spending two slots on it.
    phrase_words = {word for item in kept for word in item["name"].split()}
    single_words = 0

    for ngram, count in salient_only.most_common(pool):
        name = " ".join(ngram)

        if len(ngram) == LABEL_ONLY_WIDTH:
            if name in phrase_words or single_words >= SINGLE_WORD_LIMIT:
                continue

            # Adverbs reach here because the tagger accepts any word it cannot
            # rule out, and a bare adverb never names a topic.
            if name.endswith("ly"):
                continue

            if (
                name in STRUCTURAL_WORDS
                or name in ENTITY_NOISE_WORDS
                or name in ENTITY_HEADER_WORDS
            ):
                continue

            # "thermal ratcheting" is a term; "limiting" on its own is a verb
            # form. A rescued gerund needs a phrase around it to stand up.
            if _noun_or_adjective(name) is None:
                continue

            index = label_index
        else:
            index = lemma_index

        if not is_salient(name, index):
            continue

        if len(ngram) == LABEL_ONLY_WIDTH:
            single_words += 1

        kept.append({"name": name, "count": count, "salient": True})

    kept.sort(key=lambda item: -item["count"])

    return kept[:top_k]


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

    key = hashlib.sha1(
        f"{DF_CACHE_VERSION}::{'::'.join(ordered)}".encode("utf-8")
    ).hexdigest()[:16]
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
        # Counted at min_count=1: a term this map has never seen is treated as
        # maximally distinctive, so excluding single mentions here would hand
        # the highest score to terms that are in fact common everywhere.
        # Built with the same salience the shortlist uses, so the map covers
        # the widths that only salience admits. A term missing from the map is
        # scored as maximally distinctive, so omitting them here would hand the
        # top score to single words that are in fact common everywhere.
        index = build_salience_index(body)

        terms = {
            item["name"].lower()
            for item in candidate_names(body, top_k=400, min_count=1, salience=index)
        }
        terms |= {
            item["name"].lower()
            for item in concept_candidates(body, top_k=200, min_count=1, salience=index)
        }

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
