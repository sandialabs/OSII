import io
import os
import re
from pathlib import Path

import fitz
from typing import Any

from osii.model_clients import create_shirty_client

from osii.extraction.base import BaseExtractor, ExtractionSegment, ExtractionState
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    persist_segment,
    update_provenance,
)

# PDF extraction modes for Textract-backed extraction.
# "page" preserves page-level provenance and is the preferred default for PDFs.
# "document" minimizes requests by extracting the whole file in one call, but only
# supports chunk-level provenance.
DEFAULT_PDF_MODE = "page"


def split_paragraph_aware_word_chunks(text: str, max_words: int = 2000) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_word_count = 0

    def flush_current():
        nonlocal current_parts, current_word_count
        if current_parts:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = []
            current_word_count = 0

    for para in paragraphs:
        words = para.split()
        para_word_count = len(words)

        if para_word_count > max_words:
            flush_current()
            for i in range(0, para_word_count, max_words):
                subchunk = " ".join(words[i:i + max_words]).strip()
                if subchunk:
                    chunks.append(subchunk)
            continue

        if current_word_count + para_word_count > max_words:
            flush_current()

        current_parts.append(para)
        current_word_count += para_word_count

    flush_current()
    return chunks


class TextractExtractor(BaseExtractor):
    name = "textract"
    display_name = "Textract Extractor"
    description = (
        "Uses Shirty-hosted Textract extraction for document text. "
        "For PDFs, it defaults to page-level extraction for grounded provenance. "
        "For non-PDFs, it writes paragraph-aware text chunks into one shared extracted text file."
    )
    version = "1.1"

    def _get_shirty_client(self, api_key: str | None = None) -> Any:
        if api_key:
            old_value = os.environ.get("SHIRTY_API_KEY")
            os.environ["SHIRTY_API_KEY"] = api_key
            try:
                client = create_shirty_client()
            finally:
                if old_value is None:
                    os.environ.pop("SHIRTY_API_KEY", None)
                else:
                    os.environ["SHIRTY_API_KEY"] = old_value
            return client

        return create_shirty_client()

    def extract_text(self, file_path: Path, api_key: str | None = None) -> str:
        try:
            client = self._get_shirty_client(api_key)
        except Exception as exc:
            raise RuntimeError(f"Could not initialize Shirty client: {exc}") from exc

        try:
            with file_path.open("rb") as f:
                try:
                    document = client.extract.textract.create(file=f)
                except Exception as exc:
                    raise RuntimeError(
                        f"Shirty Textract extraction failed for source '{file_path.name}': {exc}"
                    ) from exc
        except Exception as exc:
            raise RuntimeError(f"Could not open/read source file '{file_path}': {exc}") from exc

        try:
            return document.text
        except Exception as exc:
            raise RuntimeError(
                f"Extraction returned invalid text payload for '{file_path.name}': {exc}"
            ) from exc

    def extract_pdf_page_texts(self, file_path: Path, api_key: str | None = None) -> list[str]:
        try:
            client = self._get_shirty_client(api_key)
        except Exception as exc:
            raise RuntimeError(f"Could not initialize Shirty client: {exc}") from exc

        page_texts: list[str] = []

        try:
            pdf = fitz.open(file_path)
        except Exception as exc:
            raise RuntimeError(f"Could not open PDF '{file_path}': {exc}") from exc

        try:
            for page_index in range(len(pdf)):
                out_pdf = fitz.open()
                out_pdf.insert_pdf(pdf, from_page=page_index, to_page=page_index)
                page_bytes = out_pdf.tobytes()
                out_pdf.close()

                page_file = io.BytesIO(page_bytes)
                page_file.name = f"page_{page_index + 1}.pdf"

                try:
                    document = client.extract.textract.create(file=page_file)
                except Exception as exc:
                    raise RuntimeError(
                        f"Shirty Textract extraction failed for source '{file_path.name}', page {page_index + 1}: {exc}"
                    ) from exc

                try:
                    page_text = document.text or ""
                except Exception as exc:
                    raise RuntimeError(
                        f"Extraction returned invalid page text payload for '{file_path.name}', page {page_index + 1}: {exc}"
                    ) from exc

                page_texts.append(page_text)

        finally:
            pdf.close()

        return page_texts

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
        shirty_api_key = extractor_config.get("shirty_api_key")
        max_words = int(extractor_config.get("max_words", 2000))

        pdf_mode = str(extractor_config.get("pdf_mode", DEFAULT_PDF_MODE)).strip().lower()
        if pdf_mode not in {"page", "document"}:
            raise RuntimeError(f"Unsupported pdf_mode for textract extractor: {pdf_mode}")

        is_pdf = str(doc_ctx.get("mime") or "").lower() == "application/pdf"

        tools = {
            "text_tool": "textract",
            "shirty": "enabled",
        }
        config = {
            "expert_context_used": bool(expert_context),
            "max_words": max_words,
            "segment_storage": "shared_text_file",
            "pdf_mode": pdf_mode if is_pdf else None,
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
            if is_pdf and pdf_mode == "page":
                page_texts = self.extract_pdf_page_texts(doc_ctx["src"], api_key=shirty_api_key)
                state.units_attempted = len(page_texts)

                for page_num, page_text in enumerate(page_texts, start=1):
                    seg = ExtractionSegment(
                        seg=page_num,
                        type="page",
                        text=page_text,
                        source_origin={
                            "source_type": "pdf",
                            "unit_type": "page",
                            "page": page_num,
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

                if not page_texts:
                    state.warnings.append("No page text content extracted.")

            else:
                text = self.extract_text(doc_ctx["src"], api_key=shirty_api_key)
                chunks = split_paragraph_aware_word_chunks(text, max_words=max_words)
                state.units_attempted = len(chunks)

                for i, chunk in enumerate(chunks, start=1):
                    seg = ExtractionSegment(
                        seg=i,
                        type="chunk",
                        text=chunk,
                        source_origin={
                            "source_type": "document",
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
    return TextractExtractor().extract(
        source_path=source_path,
        data_volume_root=data_volume_root,
        osii_store=osii_store,
        expert_context=expert_context,
        extractor_config=extractor_config,
    )
