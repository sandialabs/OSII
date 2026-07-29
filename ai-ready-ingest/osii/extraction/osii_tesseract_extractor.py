import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from osii.extraction.base import BaseExtractor, ExtractionState
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    update_provenance,
)
from osii.domain.storage.objects import (
    append_manifest_record,
    append_text_file,
)


DEFAULT_OSII_TESSERACT_URL = "http://127.0.0.1:8080"
DEFAULT_DOCX_TO_PDF_BACKEND = "libreoffice"


class OsiiTesseractExtractor(BaseExtractor):
    name = "osii_tesseract"
    display_name = "OSII-Tesseract Extractor"
    description = (
        "Uses the OSII-Tesseract OCR service for page-grounded OCR on PDFs and supported "
        "document types. Writes one manifest-backed text segment per page with page-level provenance."
    )
    version = "1.0"

    def _base_url(self, extractor_config: dict | None = None) -> str:
        extractor_config = extractor_config or {}
        return str(
            extractor_config.get(
                "osii_tesseract_base_url",
                os.getenv("OSII_TESSERACT_URL", DEFAULT_OSII_TESSERACT_URL),
            )
        ).rstrip("/")

    def _language(self, extractor_config: dict | None = None) -> str:
        extractor_config = extractor_config or {}
        return str(extractor_config.get("language", "en")).strip() or "en"

    def _docx_to_pdf_backend(self, extractor_config: dict | None = None) -> str:
        extractor_config = extractor_config or {}
        return str(
            extractor_config.get(
                "docx_to_pdf_backend",
                os.getenv("DOCX_TO_PDF_BACKEND", DEFAULT_DOCX_TO_PDF_BACKEND),
            )
        ).strip().lower()

    def _ocr_document(self, file_path: Path, mime: str, extractor_config: dict | None = None) -> dict:
        url = f"{self._base_url(extractor_config)}/ocr/document"
        language = self._language(extractor_config)

        try:
            with file_path.open("rb") as f:
                response = requests.post(
                    url,
                    files={"file": (file_path.name, f, mime)},
                    data={"language": language},
                    timeout=600,
                )
        except Exception as exc:
            raise RuntimeError(f"Could not send file to OSII-Tesseract service at {url}: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"OSII-Tesseract document OCR failed for '{file_path.name}': "
                f"HTTP {response.status_code} - {response.text[:1000]}"
            )

        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError(f"OSII-Tesseract returned invalid JSON for '{file_path.name}': {exc}") from exc

    def _convert_docx_to_pdf_libreoffice(self, source_path: Path) -> Path:
        soffice = shutil.which("soffice")
        if not soffice:
            raise RuntimeError(
                "LibreOffice conversion requested but 'soffice' was not found on PATH."
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="osii_docx_pdf_")).resolve()
        out_dir = temp_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice DOCX->PDF conversion failed for '{source_path.name}': "
                f"{result.stderr or result.stdout}"
            )

        pdf_path = out_dir / f"{source_path.stem}.pdf"
        if not pdf_path.exists():
            raise RuntimeError(
                f"LibreOffice conversion completed but PDF output was not found: {pdf_path}"
            )

        return pdf_path

    def _convert_source_to_pdf_if_needed(
        self,
        source_path: Path,
        mime: str,
        extractor_config: dict | None = None,
    ) -> tuple[Path, str, bool]:
        mime = (mime or "").lower()

        if mime == "application/pdf":
            return source_path, "application/pdf", False

        if mime in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }:
            backend = self._docx_to_pdf_backend(extractor_config)
            if backend == "libreoffice":
                pdf_path = self._convert_docx_to_pdf_libreoffice(source_path)
                return pdf_path, "application/pdf", True
            raise RuntimeError(f"Unsupported DOCX->PDF conversion backend: {backend}")

        raise RuntimeError(
            f"osii_tesseract currently supports PDFs directly and DOCX via conversion, not mime '{mime}'."
        )

    def _page_text(self, page_record: dict) -> str:
        parts = []
        for item in page_record.get("results", []):
            text = item.get("text")
            if not text:
                continue
            text = str(text).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

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
        page_limit_raw = extractor_config.get("page_limit")
        page_limit = int(page_limit_raw) if page_limit_raw not in (None, "", "none") else None

        effective_path = None
        effective_mime = None
        converted_to_pdf = False
        converted_pdf_path = None

        tools = {
            "ocr_service": "osii_tesseract",
            "osii_tesseract_base_url": self._base_url(extractor_config),
            "docx_to_pdf_backend": self._docx_to_pdf_backend(extractor_config),
        }
        config = {
            "language": self._language(extractor_config),
            "page_limit": page_limit,
            "expert_context_used": bool(expert_context),
            "segment_storage": "shared_text_file",
            "segmentation": "page",
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
            effective_path, effective_mime, converted_to_pdf = self._convert_source_to_pdf_if_needed(
                doc_ctx["src"],
                doc_ctx["mime"],
                extractor_config,
            )

            if converted_to_pdf:
                converted_pdf_path = effective_path
                config["converted_to_pdf"] = True
                config["conversion_source_mime"] = doc_ctx["mime"]

            payload = self._ocr_document(effective_path, effective_mime, extractor_config)
            pages = payload.get("pages", [])
            if page_limit is not None:
                pages = pages[:page_limit]

            state.units_attempted = len(pages)
            source_type = "pdf"

            for i, page_record in enumerate(pages, start=1):
                page_num = int(page_record.get("page", i))
                page_text = self._page_text(page_record)

                char_start, char_end = append_text_file(
                    osii_store=osii_store,
                    file_id=doc_ctx["file_id"],
                    text=page_text,
                )

                record = {
                    "kind": "text",
                    "id": f"seg-{i:06d}",
                    "path": "text.txt",
                    "type": "page",
                    "span": {
                        "char_start": char_start,
                        "char_end": char_end,
                    },
                    "source_origin": {
                        "source_type": source_type,
                        "unit_type": "page",
                        "page": page_num,
                        "page_width": page_record.get("width"),
                        "page_height": page_record.get("height"),
                    },
                }

                append_manifest_record(
                    osii_store=osii_store,
                    file_id=doc_ctx["file_id"],
                    record=record,
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

            if not pages:
                state.warnings.append("No pages returned from OSII-Tesseract OCR service.")

            final_status = "done"

        except Exception as exc:
            state.error = str(exc)
            final_status = "error"

        finally:
            if converted_pdf_path is not None and converted_pdf_path.exists():
                try:
                    shutil.rmtree(converted_pdf_path.parent.parent, ignore_errors=True)
                except Exception:
                    pass

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
    return OsiiTesseractExtractor().extract(
        source_path=source_path,
        data_volume_root=data_volume_root,
        osii_store=osii_store,
        expert_context=expert_context,
        extractor_config=extractor_config,
    )