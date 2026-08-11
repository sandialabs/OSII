from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re

from osii.domain.artifacts.enrichment_artifacts import write_scope_enrichment_variant
from osii.enrichment.base import BaseEnricher, EnrichmentState
from osii.enrichment.common import collect_scope_texts


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENTENCE_RE = re.compile(r"[^.!?\n]+")
ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{2,}|[A-Z][a-z][A-Za-z0-9'.-]*)"
    r"(?:\s+(?:(?:of|the|and|for|in|on|&|de|van)\s+)?"
    r"(?:[A-Z]{2,}|[A-Z][a-z][A-Za-z0-9'.-]*)){0,5}\b"
)

FUNCTION_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "before",
    "being", "between", "both", "but", "by", "can", "could", "did", "do", "does",
    "during", "each", "for", "from", "had", "has", "have", "he", "her", "here",
    "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "may", "might", "more", "most", "must", "no", "not", "of", "on", "or", "our",
    "ours", "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "then", "there", "these", "they", "this", "those", "through",
    "to", "under", "until", "up", "us", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "why", "will", "with", "would", "you", "your",
}

COMMON_VERBS = {
    "add", "allow", "appear", "apply", "become", "begin", "build", "call", "change",
    "check", "choose", "come", "contain", "continue", "create", "define", "describe",
    "display", "do", "drive", "enable", "end", "explain", "find", "follow", "generate",
    "get", "give", "go", "include", "keep", "know", "let", "make", "mean", "move",
    "need", "open", "provide", "read", "record", "reduce", "require", "return", "run",
    "save", "see", "select", "set", "show", "start", "stop", "support", "take", "tell",
    "think", "try", "turn", "use", "want", "work", "write",
}

ADJECTIVE_WORDS = {
    "available", "canonical", "chemical", "current", "different", "digital", "direct",
    "effective", "electrical", "experimental", "external", "final", "fluid", "general",
    "grounded", "high", "important", "individual", "large", "local", "low", "main",
    "mechanical", "multiple", "new", "normal", "optional", "physical", "primary",
    "reasonable", "remote", "semantic", "shared", "simple", "small", "standard",
    "technical", "thermal", "useful", "virtual",
}

ADJECTIVE_SUFFIXES = (
    "able", "al", "ary", "ful", "ible", "ic", "ical", "ish", "ive", "less", "ory", "ous",
)

IRREGULAR_LEMMAS = {
    "analyses": "analysis",
    "children": "child",
    "criteria": "criterion",
    "data": "data",
    "indices": "index",
    "matrices": "matrix",
    "men": "man",
    "people": "person",
    "women": "woman",
}

ENTITY_STARTER_WORDS = {
    "A", "An", "And", "As", "At", "But", "For", "From", "He", "Here", "However",
    "I", "If", "In", "It", "Its", "No", "On", "She", "So", "The", "Then", "There",
    "These", "They", "This", "Those", "To", "We", "When", "Where", "Which", "While",
    "With", "You",
}

ORGANIZATION_MARKERS = {
    "agency", "association", "center", "centre", "college", "company", "corporation",
    "department", "foundation", "group", "institute", "laboratories", "laboratory",
    "office", "organization", "university",
}


def _lemma(word: str, adjective: bool) -> str:
    value = word.lower().strip("'-")
    if value in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[value]
    if adjective:
        if value.endswith("iest") and len(value) > 5:
            return value[:-4] + "y"
        if value.endswith("ier") and len(value) > 4:
            return value[:-3] + "y"
        if value.endswith("est") and len(value) > 5:
            root = value[:-3]
            return root[:-1] if len(root) > 2 and root[-1] == root[-2] else root
        if value.endswith("er") and len(value) > 4:
            root = value[:-2]
            return root[:-1] if len(root) > 2 and root[-1] == root[-2] else root
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith(("ches", "shes", "sses", "xes", "zes")) and len(value) > 5:
        return value[:-2]
    if value.endswith("s") and not value.endswith(("ss", "us", "is")) and len(value) > 3:
        return value[:-1]
    return value


def _noun_or_adjective(word: str) -> tuple[str, str] | None:
    value = word.lower().strip("'-")
    if len(value) < 3 or value in FUNCTION_WORDS or value in COMMON_VERBS:
        return None
    adjective = value in ADJECTIVE_WORDS or value.endswith(ADJECTIVE_SUFFIXES)
    if not adjective and value.endswith(("ing", "ed")):
        return None
    return _lemma(value, adjective), "adjective" if adjective else "noun"


class NounAdjectiveNgramEnricher(BaseEnricher):
    name = "noun_adjective_ngrams"
    display_name = "Noun/adjective phrase keywords"
    description = "Ranks 2-, 3-, and 4-grams of locally lemmatized English nouns and adjectives."
    version = "1.0"

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        config = enricher_config or {}
        top_k = max(1, min(int(config.get("top_k", 20)), 200))
        state = EnrichmentState()
        try:
            texts, total_chars = collect_scope_texts(osii_store, scope)
            state.input_objects_seen = len(texts)
            state.input_chars_read = total_chars
            counts: Counter[tuple[str, ...]] = Counter()
            documents_by_ngram: dict[tuple[str, ...], set[str]] = defaultdict(set)

            for item in texts:
                seen_in_document: set[tuple[str, ...]] = set()
                for sentence in SENTENCE_RE.findall(item["text"]):
                    lemmas = [
                        tagged[0]
                        for token in WORD_RE.findall(sentence)
                        if (tagged := _noun_or_adjective(token)) is not None
                    ]
                    for width in (2, 3, 4):
                        for offset in range(0, len(lemmas) - width + 1):
                            ngram = tuple(lemmas[offset:offset + width])
                            counts[ngram] += 1
                            seen_in_document.add(ngram)
                for ngram in seen_in_document:
                    documents_by_ngram[ngram].add(item["file_id"])

            ranked = sorted(
                counts,
                key=lambda ngram: (-counts[ngram], -len(ngram), " ".join(ngram)),
            )[:top_k]
            rows = [
                {
                    "rank": index,
                    "keyword": " ".join(ngram),
                    "n": len(ngram),
                    "frequency": counts[ngram],
                    "document_frequency": len(documents_by_ngram[ngram]),
                }
                for index, ngram in enumerate(ranked, start=1)
            ]
            row_provenance = [
                [{"file_id": file_id} for file_id in sorted(documents_by_ngram[ngram])]
                for ngram in ranked
            ]
            result = write_scope_enrichment_variant(
                osii_store,
                scope,
                kind="keywords",
                method=self.name,
                payload={
                    "artifact_type": "table",
                    "title": "Noun and adjective phrase keywords",
                    "description": "Top 20 frequency-ranked 2-, 3-, and 4-grams after local English noun/adjective filtering and lemmatization.",
                    "columns": [
                        {"key": "rank", "label": "Rank", "data_type": "integer"},
                        {"key": "keyword", "label": "Keyword phrase", "data_type": "string"},
                        {"key": "n", "label": "N-gram", "data_type": "integer"},
                        {"key": "frequency", "label": "Frequency", "data_type": "integer"},
                        {"key": "document_frequency", "label": "Documents", "data_type": "integer"},
                    ],
                    "rows": rows,
                    "row_provenance": row_provenance,
                },
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "tagger": "osii-local-english-morphology-v1",
                    "ngram_sizes": [2, 3, 4],
                    "top_k": top_k,
                    "input_object_count": len(texts),
                    "input_chars": total_chars,
                    "expert_context_used": bool(expert_context),
                },
            )
            state.output_files_written = 2
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error) from exc


def _entity_type(name: str) -> str:
    tokens = [token.lower().strip(".'") for token in name.split()]
    if any(token in ORGANIZATION_MARKERS for token in tokens):
        return "organization_candidate"
    if len(tokens) == 1 and name.replace(".", "").isupper():
        return "acronym_candidate"
    if 2 <= len(tokens) <= 4 and all(token not in {"of", "the", "and", "for", "in", "on"} for token in tokens):
        return "person_or_named_thing_candidate"
    return "named_entity_candidate"


class EntityCandidateEnricher(BaseEnricher):
    name = "entity_candidates"
    display_name = "Named entity candidates"
    description = "Creates a grounded entity list from repeated capitalized names and acronyms."
    version = "1.0"

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        config = enricher_config or {}
        top_k = max(1, min(int(config.get("top_k", 50)), 500))
        state = EnrichmentState()
        try:
            texts, total_chars = collect_scope_texts(osii_store, scope)
            state.input_objects_seen = len(texts)
            state.input_chars_read = total_chars
            variants: dict[str, Counter[str]] = defaultdict(Counter)
            mentions: dict[str, list[dict]] = defaultdict(list)
            documents_by_entity: dict[str, set[str]] = defaultdict(set)

            for item in texts:
                for match in ENTITY_RE.finditer(item["text"]):
                    name = " ".join(match.group(0).split()).strip(" .")
                    words = name.split()
                    if not name or (len(words) == 1 and name in ENTITY_STARTER_WORDS):
                        continue
                    key = name.casefold()
                    variants[key][name] += 1
                    documents_by_entity[key].add(item["file_id"])
                    if len(mentions[key]) < 25:
                        mentions[key].append({
                            "file_id": item["file_id"],
                            "char_start": match.start(),
                            "char_end": match.end(),
                            "source_origin": {"representation": item.get("representation")},
                        })

            eligible = [
                key
                for key, names in variants.items()
                if sum(names.values()) >= 2
                or any(len(name.split()) > 1 or name.isupper() for name in names)
            ]
            eligible.sort(
                key=lambda key: (
                    -sum(variants[key].values()),
                    -len(documents_by_entity[key]),
                    key,
                )
            )
            entities = []
            for key in eligible[:top_k]:
                names = variants[key]
                canonical = sorted(names, key=lambda name: (-names[name], -len(name), name))[0]
                entity_id = f"entity-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"
                entities.append({
                    "id": entity_id,
                    "name": canonical,
                    "entity_type": _entity_type(canonical),
                    "aliases": sorted(name for name in names if name != canonical),
                    "attributes": {
                        "frequency": sum(names.values()),
                        "document_frequency": len(documents_by_entity[key]),
                    },
                    "mentions": mentions[key],
                })

            result = write_scope_enrichment_variant(
                osii_store,
                scope,
                kind="entities",
                method=self.name,
                payload={
                    "artifact_type": "entity_list",
                    "title": "Named entity candidates",
                    "description": "Repeated capitalized phrases and acronyms with grounded source mentions. Candidate types are intentionally conservative.",
                    "entities": entities,
                },
                metadata={
                    "method": self.name,
                    "version": self.version,
                    "recognizer": "osii-local-capitalized-candidates-v1",
                    "top_k": top_k,
                    "input_object_count": len(texts),
                    "input_chars": total_chars,
                    "expert_context_used": bool(expert_context),
                },
            )
            state.output_files_written = 2
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error) from exc
