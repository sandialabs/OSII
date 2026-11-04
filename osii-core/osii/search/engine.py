"""Storage-independent retrieval. Search normalization never changes evidence."""
from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import re
import threading
import unicodedata

import bm25s
import numpy as np

from osii.search.hybrid import reciprocal_rank_fusion


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)", "", text)
    return " ".join(text.casefold().split())


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[-_][^\W_]+)*", normalize(text), re.UNICODE)


def grams(word: str) -> set[str]:
    word = f" {word} "
    return {word[i:i + 3] for i in range(len(word) - 2)}


class RetrievalEngine:
    """Bounded in-memory caches rebuilt from immutable, versioned chunk rows."""

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple, tuple] = OrderedDict()
        self._lock = threading.RLock()

    def search(self, rows: list[dict], query: str, *, revision: int,
               mode: str = "hybrid", top_k: int = 10,
               query_vector: list[float] | None = None,
               embedding_model: str = "") -> tuple[list[dict], list[str]]:
        if mode not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("Unsupported retrieval mode")
        if not rows or not tokens(query):
            return [], []
        # Scope has already constrained rows. Ranking cannot starve a small scope.
        key = (revision, tuple(row["chunk_id"] for row in rows))
        with self._lock:
            if key not in self._cache:
                corpus = [tokens(row["text"]) for row in rows]
                vocabulary = set(word for words in corpus for word in words)
                bm = bm25s.BM25()
                if vocabulary:
                    bm.index(corpus, show_progress=False)
                self._cache[key] = (bm, vocabulary, corpus)
                while len(self._cache) > 4:
                    self._cache.popitem(last=False)
            bm, vocabulary, corpus = self._cache[key]
        lists: list[list[dict]] = []
        channels: list[str] = []
        limit = min(len(rows), max(top_k * 5, 50))

        def result(index: int, score: float, channel: str) -> dict:
            row = rows[index]
            return {**row, "score": float(score), "match_type": channel,
                    "snippet": row["text"][:700]}

        if mode != "semantic":
            known = [word for word in tokens(query) if word in vocabulary]
            if known:
                ids, scores = bm.retrieve([known], k=limit, show_progress=False)
                lexical = [result(int(i), float(s), "lexical")
                           for i, s in zip(ids[0], scores[0]) if float(s) > 0]
                if lexical:
                    lists.append(lexical)
                    channels.append("bm25")
            # Bounded vocabulary expansion handles OCR damage without changing
            # source text or inventing numeric identifiers. Exact terms dominate.
            query_words = tokens(query)
            alternatives = {}
            for word in query_words:
                choices = [(word, 1.0)] if word in vocabulary else []
                if len(word) >= 4 and not word.isdigit():
                    query_grams = grams(word)
                    for candidate in vocabulary:
                        if abs(len(candidate) - len(word)) > 2:
                            continue
                        candidate_grams = grams(candidate)
                        overlap = len(query_grams & candidate_grams) / max(1, len(query_grams | candidate_grams))
                        if overlap >= .25:
                            similarity = SequenceMatcher(None, word, candidate).ratio()
                            if similarity >= .72:
                                choices.append((candidate, similarity * .8))
                alternatives[word] = sorted(choices, key=lambda item: (-item[1], item[0]))[:8]
            fuzzy = []
            for i, words in enumerate(corpus):
                present = set(words)
                score = sum(max((s for term, s in choices if term in present), default=0)
                            for choices in alternatives.values()) / len(query_words)
                if score > 0:
                    fuzzy.append(result(i, score, "character"))
            fuzzy.sort(key=lambda row: (-row["score"], row["chunk_id"]))
            if fuzzy:
                lists.append(fuzzy[:limit])
                channels.append("character")
        if mode != "lexical" and query_vector:
            q = np.asarray(query_vector, dtype=np.float32)
            qnorm = float(np.linalg.norm(q))
            semantic = []
            for i, row in enumerate(rows):
                values = row.get("embedding")
                if not values or row.get("embedding_model") != embedding_model or len(values) != len(q):
                    continue
                vector = np.asarray(values, dtype=np.float32)
                denominator = qnorm * float(np.linalg.norm(vector))
                score = float(vector @ q / denominator) if denominator else 0
                if score > 0:
                    semantic.append(result(i, score, "semantic"))
            semantic.sort(key=lambda row: (-row["score"], row["chunk_id"]))
            if semantic:
                lists.append(semantic[:limit])
                channels.append("semantic")
        if not lists:
            return [], channels
        fused = reciprocal_rank_fusion(lists) if len(lists) > 1 else lists[0]
        # Remove largely overlapping windows without losing the original spans.
        selected = []
        for row in fused:
            duplicate = any(row["file_id"] == old["file_id"] and
                            max(0, min(row["char_end"], old["char_end"]) - max(row["char_start"], old["char_start"])) /
                            max(1, min(row["char_end"] - row["char_start"], old["char_end"] - old["char_start"])) >= .65
                            for old in selected)
            if not duplicate:
                selected.append(row)
            if len(selected) == top_k:
                break
        return selected, channels
