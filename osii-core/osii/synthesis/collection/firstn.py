from pathlib import Path

from osii.domain.artifacts.synth_artifacts import write_collection_synthesis_variant
from osii.domain.read.synthesis import get_synth_text
from osii.domain.scopes.collections import list_collection_documents
from osii.domain.storage.objects import object_text_path
from osii.synthesis.collection.base import BaseCollectionSynthesizer, CollectionSynthesisState


class CollectionFirstNSynthesizer(BaseCollectionSynthesizer):
    name = "collection_firstn"
    display_name = "Collection FirstN Synthesizer"
    description = (
        "Builds a simple collection-level synthesis by concatenating member syntheses "
        "or fallback object text and writing the first N characters."
    )
    version = "1.0"
    scope = "collection"
    mode = "summary"
    domain = "generic"

    def describe(self) -> dict:
        data = super().describe()
        data["mode"] = self.mode
        data["domain"] = self.domain
        return data

    def synthesize_collection(
        self,
        *,
        osii_store: Path,
        collection_id: str,
        expert_context: str | None = None,
        synthesizer_config: dict | None = None,
    ) -> dict:
        synthesizer_config = synthesizer_config or {}
        max_chars = int(synthesizer_config.get("max_chars", 4000))

        state = CollectionSynthesisState()

        file_ids = list_collection_documents(osii_store, collection_id)
        parts = []

        for file_id in file_ids:
            synth = get_synth_text(osii_store, file_id)
            if synth:
                parts.append(synth)
                continue

            text_path = object_text_path(osii_store, file_id)
            if text_path.exists():
                parts.append(text_path.read_text(encoding="utf-8"))

        state.member_objects_seen = len(file_ids)
        combined = "\n\n".join(parts).strip()
        state.input_chars_read = len(combined)

        summary = combined[:max_chars].strip()

        result = write_collection_synthesis_variant(
            osii_store,
            collection_id,
            method=self.name,
            text=summary,
            metadata={
                "method": self.name,
                "max_chars": max_chars,
                "member_count": len(file_ids),
            },
        )
        state.output_chars_written = len(summary)

        return result