from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import docx2txt
import fitz

from osii.extraction.base import BaseExtractor, ExtractionSegment, ExtractionState
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    persist_segment,
    update_provenance,
)


TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".htm",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".py",
    ".rst",
    ".sql",
    ".toml",
    ".ts",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def _chunk_text(text: str, chunk_chars: int) -> list[str]:
    clean = (text or "").strip()
    return [clean[index:index + chunk_chars] for index in range(0, len(clean), chunk_chars)]


def _office_zip_text(path: Path) -> str:
    """Return readable text from modern Office XML packages without a service."""

    parts: list[str] = []
    with zipfile.ZipFile(path) as package:
        names = sorted(
            name
            for name in package.namelist()
            if name.endswith(".xml")
            and (
                name.startswith("ppt/slides/")
                or name.startswith("xl/sharedStrings")
                or name.startswith("xl/worksheets/")
            )
        )
        for name in names:
            try:
                root = ElementTree.fromstring(package.read(name))
            except ElementTree.ParseError:
                continue
            text = " ".join(
                value.strip()
                for value in root.itertext()
                if value and value.strip()
            )
            if text:
                parts.append(text)
    return "\n\n".join(parts)


class NativeTextExtractor(BaseExtractor):
    """Small host-native extractor for rapid development without containers."""

    name = "native_text"
    display_name = "Native Python Text Extractor"
    description = (
        "Runs entirely in the OSII Python process. Supports text files, text-layer "
        "PDFs, DOCX, PPTX, and XLSX without Tika or OCR."
    )
    version = "1.0"

    def _units(self, path: Path, chunk_chars: int) -> list[tuple[str, str, dict]]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            units = []
            with fitz.open(path) as document:
                for page_index, page in enumerate(document, start=1):
                    text = page.get_text("text").strip()
                    if text:
                        units.append(
                            (
                                "page",
                                text,
                                {
                                    "source_type": "pdf",
                                    "unit_type": "page",
                                    "page": page_index,
                                },
                            )
                        )
            return units

        if suffix == ".docx":
            text = docx2txt.process(str(path)) or ""
        elif suffix in {".pptx", ".xlsx"}:
            text = _office_zip_text(path)
        elif suffix == ".rtf":
            raw = path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", raw)
        elif suffix in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raise RuntimeError(
                f"The host-native extractor does not support '{suffix or 'files without an extension'}'. "
                "Exclude that file type during development or use make dev-containers "
                "to test the Tika/OCR deployment path."
            )

        return [
            (
                "chunk",
                chunk,
                {
                    "source_type": "native_text",
                    "unit_type": "chunk",
                    "chunk_index": index,
                },
            )
            for index, chunk in enumerate(_chunk_text(text, chunk_chars), start=1)
        ]

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
        config = extractor_config or {}
        chunk_chars = int(config.get("chunk_chars", 4000))
        provenance_config = {
            "chunk_chars": chunk_chars,
            "expert_context_used": bool(expert_context),
            "segment_storage": "shared_text_file",
            **({"fallback_from": config["fallback_from"]} if config.get("fallback_from") else {}),
        }

        initialize_bundle(osii_store=osii_store, doc_ctx=doc_ctx)
        update_provenance(
            osii_store=osii_store,
            doc_ctx=doc_ctx,
            extractor_name=self.name,
            extractor_version=self.version,
            status="running",
            tools={"text_tool": "native_python"},
            config=provenance_config,
            state=state,
        )

        try:
            units = self._units(doc_ctx["src"], chunk_chars)
            state.units_attempted = len(units)
            for index, (unit_type, text, source_origin) in enumerate(units, start=1):
                persist_segment(
                    osii_store=osii_store,
                    doc_ctx=doc_ctx,
                    segment=ExtractionSegment(
                        seg=index,
                        type=unit_type,
                        text=text,
                        source_origin=source_origin,
                    ),
                    shared_text_file=True,
                )
                state.segments_written += 1
                state.units_completed += 1
            if not units and doc_ctx["src"].suffix.lower() == ".pdf":
                raise RuntimeError(
                    "No embedded PDF text was found. This appears to be a scanned "
                    "PDF and requires an OCR extractor."
                )
            if not units:
                state.warnings.append("No text content was found.")
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
            tools={"text_tool": "native_python"},
            config=provenance_config,
            state=state,
        )
        if state.error:
            raise RuntimeError(state.error)
        return build_result_dict(doc_ctx)
