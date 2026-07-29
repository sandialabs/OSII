import os
from pathlib import Path

import requests

from osii.extraction.base import BaseExtractor, ExtractionSegment, ExtractionState
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    persist_segment,
    update_provenance,
)


def chunk_text(text: str, chunk_chars: int = 4000) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)]


class TikaCatchallExtractor(BaseExtractor):
    name = "tika_catchall"
    display_name = "Tika Catchall Extractor"
    description = (
        "Uses Apache Tika as a general-purpose fallback extractor for text-bearing files. "
        "Best when simple plain-text extraction is sufficient and no specialized extractor exists."
    )
    version = "1.0"

    def extract_text(self, file_path: Path, mime: str) -> str:
        tika_url = os.getenv("TIKA_URL", "http://localhost:9998").rstrip("/")
        endpoint = f"{tika_url}/tika"

        try:
            with file_path.open("rb") as f:
                response = requests.put(
                    endpoint,
                    data=f,
                    headers={
                        "Accept": "text/plain",
                        "Content-Type": mime,
                    },
                    timeout=300,
                )
        except Exception as exc:
            raise RuntimeError(f"Could not send file to Tika at {endpoint}: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"Tika extraction failed for source '{file_path.name}': "
                f"HTTP {response.status_code} - {response.text[:1000]}"
            )

        return response.text

    def extract(
        self,
        *,
        source_path: Path,
        data_volume_root: Path,
        osii_store: Path,
        expert_context: str | None = None,
        extractor_config: dict | None = None,
    ) -> dict:
        doc_ctx = init_doc_context(source_path, data_volume_root)
        state = ExtractionState()

        extractor_config = extractor_config or {}
        chunk_chars = int(extractor_config.get("chunk_chars", 4000))

        tools = {
            "text_tool": "tika",
            "tika_url": os.getenv("TIKA_URL", "http://localhost:9998"),
        }
        config = {
            "chunk_chars": chunk_chars,
            "expert_context_used": bool(expert_context),
            "segment_storage": "shared_text_file",
        }

        initialize_bundle(osii_store=osii_store, doc_ctx=doc_ctx)
        update_provenance(
            osii_store=osii_store,
            doc_ctx=doc_ctx,
            extractor_name=self.name,
            extractor_version=self.version,
            status="running",
            tools=tools,
            config=config,
            state=state,
        )

        try:
            text = self.extract_text(doc_ctx["src"], doc_ctx["mime"])
            chunks = chunk_text(text, chunk_chars=chunk_chars)
            state.units_attempted = len(chunks)

            for i, chunk in enumerate(chunks, start=1):
                seg = ExtractionSegment(
                    seg=i,
                    type="chunk",
                    text=chunk,
                    source_origin={
                        "source_type": "generic_text",
                        "unit_type": "chunk",
                        "chunk_index": i,
                    },
                    related_ids=[],
                )
                persist_segment(
                    osii_store=osii_store,
                    doc_ctx=doc_ctx,
                    segment=seg,
                    shared_text_file=True,
                )
                state.segments_written += 1
                state.units_completed += 1

                update_provenance(
                    osii_store=osii_store,
                    doc_ctx=doc_ctx,
                    extractor_name=self.name,
                    extractor_version=self.version,
                    status="running",
                    tools=tools,
                    config=config,
                    state=state,
                )

            if not chunks:
                state.warnings.append("No text content extracted.")

            final_status = "done"

        except Exception as exc:
            state.error = str(exc)
            final_status = "error"

        update_provenance(
            osii_store=osii_store,
            doc_ctx=doc_ctx,
            extractor_name=self.name,
            extractor_version=self.version,
            status=final_status,
            tools=tools,
            config=config,
            state=state,
        )

        if state.error:
            raise RuntimeError(state.error)

        return build_result_dict(doc_ctx)


def extract(
    *,
    source_path: Path,
    data_volume_root: Path,
    osii_store: Path,
    expert_context: str | None = None,
    extractor_config: dict | None = None,
) -> dict:
    return TikaCatchallExtractor().extract(
        source_path=source_path,
        data_volume_root=data_volume_root,
        osii_store=osii_store,
        expert_context=expert_context,
        extractor_config=extractor_config,
    )