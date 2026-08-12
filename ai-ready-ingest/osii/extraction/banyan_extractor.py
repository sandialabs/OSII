import base64
import io
import json
import os
from pathlib import Path

import fitz
import requests
from PIL import Image

from osii.extraction.base import (
    BaseExtractor,
    ExtractionArtifact,
    ExtractionSegment,
    ExtractionState,
)
from osii.extraction.common import (
    build_result_dict,
    init_doc_context,
    initialize_bundle,
    persist_artifact,
    persist_segment,
    update_provenance,
)

DEFAULT_NEMOTRON_BASE_URL = ""
DEFAULT_NEMOTRON_MODEL = "nvidia/nemoretriever-parse"


class PdfDefaultExtractor(BaseExtractor):
    name = "pdf_default"
    display_name = "Default PDF Extractor"
    description = (
        "Renders PDF pages to images, sends each page to Nemotron Parse, "
        "writes page text into one shared extracted text file, and crops any Picture regions into artifacts."
    )
    version = "1.0"

    def _nemotron_base_url(self, extractor_config: dict | None = None) -> str:
        extractor_config = extractor_config or {}
        base_url = str(
            extractor_config.get("nemotron_base_url", os.getenv("NEMOTRON_BASE_URL", DEFAULT_NEMOTRON_BASE_URL))
        ).rstrip("/")
        if not base_url:
            raise RuntimeError(
                "The Nemotron PDF extractor requires NEMOTRON_BASE_URL; "
                "select the bundled Tesseract extractor for offline use."
            )
        return base_url

    def _nemotron_model(self, extractor_config: dict | None = None) -> str:
        extractor_config = extractor_config or {}
        return str(
            extractor_config.get("nemotron_model", os.getenv("NEMOTRON_MODEL", DEFAULT_NEMOTRON_MODEL))
        )

    def _render_page_image(self, page: fitz.Page) -> Image.Image:
        pix = page.get_pixmap()
        mode = "RGB" if pix.alpha == 0 else "RGBA"
        return Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    def _image_to_data_url(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{image_b64}"

    def _call_nemotron(self, image: Image.Image, extractor_config: dict | None = None) -> dict:
        image_url = self._image_to_data_url(image)

        payload = {
            "model": self._nemotron_model(extractor_config),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            "temperature": max(
                0.0,
                min(float((extractor_config or {}).get("temperature", 0.0)), 2.0),
            ),
        }

        r = requests.post(
            f"{self._nemotron_base_url(extractor_config)}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=300,
        )

        if r.status_code >= 400:
            raise RuntimeError(
                f"Nemotron parse failed: HTTP {r.status_code} - {r.text[:2000]}"
            )

        return r.json()

    def _load_boxes(self, response_json: dict) -> list[dict]:
        tool_calls = response_json["choices"][0]["message"]["tool_calls"]
        if not tool_calls:
            raise ValueError("No tool_calls found in Nemotron response")

        args_str = tool_calls[0]["function"]["arguments"]
        parsed = json.loads(args_str)

        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], list):
            boxes = parsed[0]
        else:
            boxes = parsed

        if not isinstance(boxes, list):
            raise ValueError(f"Expected list of boxes, got: {type(boxes)}")

        return boxes

    def _page_text_from_boxes(self, boxes: list[dict]) -> str:
        parts = []
        for item in boxes:
            text = item.get("text", "")
            if text is None:
                continue
            text = text.strip()
            if not text:
                continue
            parts.append(text)
        return "\n\n".join(parts).strip()

    def _bbox_pixels(self, bbox: dict, width: int, height: int) -> tuple[int, int, int, int]:
        xmin = int(bbox.get("xmin", 0) * width)
        ymin = int(bbox.get("ymin", 0) * height)
        xmax = int(bbox.get("xmax", 0) * width)
        ymax = int(bbox.get("ymax", 0) * height)

        if xmin > xmax:
            xmin, xmax = xmax, xmin
        if ymin > ymax:
            ymin, ymax = ymax, ymin

        xmin = max(0, min(width, xmin))
        xmax = max(0, min(width, xmax))
        ymin = max(0, min(height, ymin))
        ymax = max(0, min(height, ymax))

        return xmin, ymin, xmax, ymax

    def _extract_picture_artifacts(
        self,
        *,
        page_num: int,
        image: Image.Image,
        boxes: list[dict],
    ) -> list[ExtractionArtifact]:
        artifacts = []
        width, height = image.size

        for item in boxes:
            if item.get("type") != "Picture":
                continue

            bbox = item.get("bbox", {})
            if not isinstance(bbox, dict):
                continue

            xmin, ymin, xmax, ymax = self._bbox_pixels(bbox, width, height)
            if xmax <= xmin or ymax <= ymin:
                continue

            cropped = image.crop((xmin, ymin, xmax, ymax))
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")

            artifacts.append(
                ExtractionArtifact(
                    artifact_id="",
                    kind="image",
                    type="image",
                    extension=".png",
                    data=buf.getvalue(),
                    source_origin={
                        "source_type": "pdf",
                        "unit_type": "region",
                        "page": page_num,
                        "bbox": {
                            "xmin": bbox.get("xmin", 0),
                            "ymin": bbox.get("ymin", 0),
                            "xmax": bbox.get("xmax", 0),
                            "ymax": bbox.get("ymax", 0),
                        },
                        "label": "Picture",
                    },
                    related_ids=[f"seg-{page_num:06d}"],
                )
            )

        return artifacts

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

        tools = {
            "parse_tool": "nemotron_parse",
            "nemotron_base_url": self._nemotron_base_url(extractor_config),
            "nemotron_model": self._nemotron_model(extractor_config),
        }
        config = {
            "segmentation": "page",
            "picture_extraction": True,
            "expert_context_used": bool(expert_context),
            "page_limit": page_limit,
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
            pdf = fitz.open(doc_ctx["src"])
            total_pages = len(pdf)
            if page_limit is not None:
                total_pages = min(total_pages, page_limit)

            state.units_attempted = total_pages
            global_artifact_count = 0

            for page_index in range(total_pages):
                page_num = page_index + 1
                page = pdf[page_index]
                page_image = self._render_page_image(page)

                response_json = self._call_nemotron(page_image, extractor_config)
                boxes = self._load_boxes(response_json)
                page_text = self._page_text_from_boxes(boxes)

                page_artifacts = self._extract_picture_artifacts(
                    page_num=page_num,
                    image=page_image,
                    boxes=boxes,
                )

                related_ids = []
                for artifact in page_artifacts:
                    global_artifact_count += 1
                    artifact.artifact_id = f"artifact-{global_artifact_count:06d}"
                    artifact.related_ids = [f"seg-{page_num:06d}"]
                    persist_artifact(
                        osii_store=osii_store,
                        doc_ctx=doc_ctx,
                        artifact=artifact,
                        artifact_num=global_artifact_count,
                    )
                    related_ids.append(artifact.artifact_id)
                    state.artifacts_written += 1

                seg = ExtractionSegment(
                    seg=page_num,
                    type="page",
                    text=page_text if page_text else "",
                    source_origin={
                        "source_type": "pdf",
                        "unit_type": "page",
                        "page": page_num,
                    },
                    related_ids=related_ids,
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

            final_status = "done"

        except Exception as exc:
            state.error = str(exc)
            final_status = "partial" if state.segments_written or state.artifacts_written else "error"

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

        if state.error and final_status == "error":
            raise RuntimeError(state.error)

        return build_result_dict(doc_ctx, error=state.error if final_status != "done" else None)


def extract(
    *,
    source_path: Path,
    data_volume_root: Path,
    osii_store: Path,
    expert_context: str | None = None,
    extractor_config: dict | None = None,
) -> dict:
    return PdfDefaultExtractor().extract(
        source_path=source_path,
        data_volume_root=data_volume_root,
        osii_store=osii_store,
        expert_context=expert_context,
        extractor_config=extractor_config,
    )
