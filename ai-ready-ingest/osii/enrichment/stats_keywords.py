from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from osii.domain.artifacts.enrichment_artifacts import (
    write_collection_enrichment_variant,
    write_folder_enrichment_variant,
    write_object_enrichment_variant,
    write_root_enrichment_variant,
)
from osii.enrichment.base import BaseEnricher, EnrichmentState
from osii.enrichment.common import collect_scope_texts
from osii.domain.scopes.scopes import normalize_scope_type


DEFAULT_STOPWORDS = {
    "the", "and", "for", "are", "with", "that", "this", "from", "into", "was", "were",
    "have", "has", "had", "but", "not", "you", "your", "their", "they", "them", "his",
    "her", "its", "our", "out", "all", "any", "can", "may", "will", "would", "should",
    "could", "about", "there", "which", "when", "what", "where", "while", "than", "then",
    "also", "such", "using", "used", "use", "these", "those", "within", "over", "under",
    "after", "before", "between", "because", "being", "been", "each", "other", "some",
    "more", "most", "only", "very", "into", "onto", "upon", "report", "document",
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())


class StatsKeywordsEnricher(BaseEnricher):
    name = "stats_keywords"
    display_name = "Stats Keywords Enricher"
    description = "Computes a simple frequency-based keyword list from preferred text."
    version = "1.0"

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        enricher_config: dict | None = None,
    ) -> dict:
        enricher_config = enricher_config or {}
        top_k = int(enricher_config.get("top_k", 20))
        min_count = int(enricher_config.get("min_count", 1))

        state = EnrichmentState()

        try:
            texts, total_chars = collect_scope_texts(osii_store, scope)
            state.input_objects_seen = len(texts)
            state.input_chars_read = total_chars

            counter = Counter()
            for item in texts:
                tokens = [
                    tok for tok in tokenize(item["text"])
                    if tok not in DEFAULT_STOPWORDS
                ]
                counter.update(tokens)

            keywords = [
                {"term": term, "count": count}
                for term, count in counter.most_common()
                if count >= min_count
            ][:top_k]

            payload = {
                "artifact_type": "table",
                "title": "Keyword frequencies",
                "description": "Frequency-ranked terms from preferred text.",
                "columns": [
                    {"key": "term", "label": "Term", "data_type": "string"},
                    {"key": "count", "label": "Count", "data_type": "integer"},
                ],
                "rows": keywords,
                "row_provenance": [],
                "keywords": keywords,
                "input_object_count": len(texts),
            }
            metadata = {
                "kind": "keywords",
                "method": self.name,
                "version": self.version,
                "top_k": top_k,
                "min_count": min_count,
            }

            scope_type = normalize_scope_type(scope.get("scope_type") or scope.get("type"))

            if scope_type == "object":
                file_id = scope["file_id"]
                result = write_object_enrichment_variant(
                    osii_store,
                    file_id,
                    kind="keywords",
                    method=self.name,
                    payload=payload,
                    metadata=metadata,
                )
            elif scope_type == "folder":
                folder_id = scope["folder_id"]
                result = write_folder_enrichment_variant(
                    osii_store,
                    folder_id,
                    kind="keywords",
                    method=self.name,
                    payload=payload,
                    metadata=metadata,
                )
            elif scope_type == "collection":
                collection_id = scope["collection_id"]
                result = write_collection_enrichment_variant(
                    osii_store,
                    collection_id,
                    kind="keywords",
                    method=self.name,
                    payload=payload,
                    metadata=metadata,
                )
            elif scope_type == "root":
                result = write_root_enrichment_variant(
                    osii_store,
                    kind="keywords",
                    method=self.name,
                    payload=payload,
                    metadata=metadata,
                )
            else:
                raise ValueError(f"Unsupported scope type: {scope_type}")

            state.output_files_written = 2
            return {
                "ok": True,
                "result": result,
                "error": None,
            }

        except Exception as exc:
            state.error = str(exc)
            raise RuntimeError(state.error)
