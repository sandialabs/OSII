from __future__ import annotations

import base64
import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import docx2txt
import pymupdf as fitz

from osii_processor_sdk import (
    Capability,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    create_processor_app,
)


TEXT_EXTENSIONS = {
    ".cfg", ".conf", ".css", ".csv", ".htm", ".html", ".ini", ".js",
    ".json", ".jsonl", ".log", ".md", ".py", ".rst", ".sql", ".toml",
    ".ts", ".tsv", ".txt", ".xml", ".yaml", ".yml",
}
SUPPORTED_EXTENSIONS = sorted(TEXT_EXTENSIONS | {".docx", ".pdf", ".pptx", ".rtf", ".xlsx"})


def _office_text(content: bytes) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(BytesIO(content)) as package:
        names = sorted(
            name for name in package.namelist()
            if name.endswith(".xml") and (
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
            text = " ".join(value.strip() for value in root.itertext() if value.strip())
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _chunks(text: str, chunk_chars: int) -> list[str]:
    clean = text.strip()
    return [clean[index:index + chunk_chars] for index in range(0, len(clean), chunk_chars)]


class LocalNativeTextExtractor(Extractor):
    descriptor = ProcessorDescriptor(
        name="local.native-text",
        version="1.0.0",
        display_name="Python text-layer PDF and Office extractor",
        description=(
            "Reads text already stored inside PDFs, Office documents, RTF, and common "
            "text files with Python libraries. It does not perform OCR on scanned pages."
        ),
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(
            file_extensions=SUPPORTED_EXTENSIONS,
            media_types=["application/pdf", "text/plain"],
            output_kinds=["text_segments"],
        ),
        config_schema={
            "type": "object",
            "properties": {"chunk_chars": {"type": "integer", "minimum": 256, "default": 4000}},
            "additionalProperties": False,
        },
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        document = request.document
        content = base64.b64decode(document.content_base64 or "")
        suffix = Path(document.filename).suffix.lower()
        chunk_chars = int(request.config.get("chunk_chars", 4000))
        segments: list[TextSegment] = []

        if suffix == ".pdf":
            with fitz.open(stream=content, filetype="pdf") as pdf:
                for page_number, page in enumerate(pdf, start=1):
                    text = page.get_text("text").strip()
                    if text:
                        segments.append(TextSegment(
                            id=f"page-{page_number}",
                            text=text,
                            segment_type="page",
                            source_origin={"source_type": "pdf", "unit_type": "page", "page": page_number},
                        ))
            if not segments:
                return ExtractionResponse(
                    request_id=request.request_id,
                    processor=self.descriptor,
                    segments=[],
                    warnings=["No embedded PDF text was found. This appears to require an OCR processor."],
                )
        else:
            if suffix == ".docx":
                with tempfile.NamedTemporaryFile(suffix=suffix) as temp:
                    temp.write(content)
                    temp.flush()
                    text = docx2txt.process(temp.name) or ""
            elif suffix in {".pptx", ".xlsx"}:
                text = _office_text(content)
            elif suffix == ".rtf":
                raw = content.decode("utf-8", errors="replace")
                text = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", raw)
            elif suffix in TEXT_EXTENSIONS:
                text = content.decode(str(request.config.get("encoding", "utf-8")), errors="replace")
            else:
                raise ValueError(f"Unsupported local extraction format: {suffix or 'no extension'}")

            segments = [
                TextSegment(
                    id=f"chunk-{index}",
                    text=chunk,
                    segment_type="chunk",
                    source_origin={"source_type": "native_text", "unit_type": "chunk", "chunk_index": index},
                )
                for index, chunk in enumerate(_chunks(text, chunk_chars), start=1)
            ]

        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            document_metadata={"source_filename": document.filename},
            warnings=[] if segments else ["No text content was found."],
        )


app = create_processor_app(LocalNativeTextExtractor())
