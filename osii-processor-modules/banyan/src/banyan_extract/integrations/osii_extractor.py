"""OSII Processor API adapter for Banyan's Nemotron document extraction."""

from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path
from typing import Any

from banyan_extract.processor.nemoparse_processor import NemoparseProcessor
from banyan_extract.utils.setup_nemoparse_config import get_nemoparse_config

try:
    from osii.processor_sdk import (
        Artifact,
        Capability,
        ExtractionRequest,
        ExtractionResponse,
        Extractor,
        ProcessorDescriptor,
        ProcessorKind,
        TextSegment,
        create_processor_app,
    )
except ImportError as exc:  # pragma: no cover - exercised when the optional extra is absent
    raise ImportError(
        "The OSII adapter requires the optional OSII dependencies. "
        "Install OSII, then install Banyan with 'pip install .[osii]'."
    ) from exc


SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]


class BanyanOsiiExtractor(Extractor):
    """Expose Banyan OCR as an opt-in OSII v1 extractor service.

    Each detected document element becomes an OSII text segment with its
    normalized page bounding box in source_origin. The complete unmodified
    element list is also retained as a JSON artifact for future PDF overlays.
    """

    descriptor = ProcessorDescriptor(
        name="banyan.nemotron-parse",
        version="1.2.5",
        display_name="Banyan Nemotron Parse Extractor",
        description="Nemotron document parsing with normalized element-level bounding-box provenance.",
        kind=ProcessorKind.EXTRACTOR,
        capabilities=Capability(
            file_extensions=SUPPORTED_EXTENSIONS,
            media_types=["application/pdf", "image/png", "image/jpeg", "image/tiff"],
            output_kinds=["text_segments", "banyan_bounding_boxes"],
        ),
        config_schema={
            "type": "object",
            "properties": {
                "model_name": {"type": "string"},
                "sort_by_position": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    )

    def _processor(self, config: dict[str, Any]) -> NemoparseProcessor:
        environment = get_nemoparse_config(Path(__file__).resolve().parents[3] / ".env")
        endpoint = str(environment["NEMOPARSE_ENDPOINT"] or "")
        model_name = str(config.get("model_name") or environment["NEMOPARSE_MODEL"] or "")
        if not endpoint or not model_name:
            raise ValueError("NEMOPARSE_ENDPOINT and NEMOPARSE_MODEL must be configured for the Banyan OSII extractor.")
        return NemoparseProcessor(
            endpoint_url=endpoint,
            model_name=model_name,
            api_key=environment["NEMOPARSE_API_KEY"],
            sort_by_position=bool(config.get("sort_by_position", True)),
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        document = request.document
        suffix = Path(document.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported Banyan OSII extraction format: {suffix or 'no extension'}")
        if not document.content_base64:
            raise ValueError("Banyan OSII extraction requires document.content_base64.")

        try:
            content = base64.b64decode(document.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("document.content_base64 must contain valid base64 bytes.") from exc
        processor = self._processor(request.config)
        with tempfile.TemporaryDirectory(prefix="banyan-osii-") as directory:
            temporary_path = Path(directory) / f"document{suffix}"
            temporary_path.write_bytes(content)
            output = processor.process_document(str(temporary_path), overwrite=True, draw_bboxes=False)

        if output is None:
            raise ValueError("Banyan skipped extraction because an output file already exists.")

        segments: list[TextSegment] = []
        bbox_pages: list[dict[str, Any]] = []
        for page_index, elements in enumerate(output.bboxdata, start=1):
            bbox_pages.append({"page": page_index, "elements": elements})
            for element_index, element in enumerate(elements, start=1):
                text = str(element.get("text") or "").strip()
                if not text:
                    continue
                segments.append(TextSegment(
                    id=f"page-{page_index}-element-{element_index}",
                    text=text,
                    segment_type=str(element.get("type") or "element").lower(),
                    source_origin={
                        "source_type": "banyan_nemotron_parse",
                        "unit_type": "document_element",
                        "page": page_index,
                        "bbox_coordinate_space": "normalized",
                        "bbox": element.get("bbox", {}),
                        "element_type": element.get("type"),
                    },
                ))

        bbox_artifact = Artifact(
            id="banyan-bounding-boxes",
            kind="banyan_bounding_boxes",
            media_type="application/json",
            json_data={
                "schema_version": "1.0",
                "coordinate_space": "normalized",
                "source_filename": document.filename,
                "pages": bbox_pages,
            },
            source_origin={"source_type": "banyan_nemotron_parse", "unit_type": "document"},
            metadata={"page_count": len(bbox_pages), "overlay_ready": True},
        )
        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
            artifacts=[bbox_artifact],
            document_metadata={
                "source_filename": document.filename,
                "page_count": len(bbox_pages),
                "bbox_coordinate_space": "normalized",
            },
            warnings=[] if segments else ["Nemotron returned no text-bearing document elements."],
        )


app = create_processor_app(BanyanOsiiExtractor())
