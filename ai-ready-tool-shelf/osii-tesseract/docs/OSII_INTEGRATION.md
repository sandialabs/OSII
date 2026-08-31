# OSII integration contract

This service is a specialized OCR API. It is **not** a Processor API v1 service
today. Its region-aware OCR result is consumed by OSII Core's
`OsiiTesseractExtractor` adapter, which is responsible for turning page text
and normalized geometry into canonical OSII segments and provenance.

## Endpoint OSII calls

`POST /ocr/document` accepts `multipart/form-data`:

| Field | Required | Meaning |
|---|---|---|
| `file` | yes | PDF or image source bytes |
| `language` | no | ISO 639-1 language code; defaults to `en` |

The response is JSON with a `pages` array. Each page includes 1-indexed `page`,
pixel `width` and `height`, and OCR `results`. Each result includes `text`,
normalized `bbox` `[left, top, right, bottom]`, normalized four-point
`polygon`, and confidence from `0.0` to `1.0`. Geometry has a top-left origin;
x increases right and y increases down.

OSII configures the service URL through `OSII_TESSERACT_URL` (or the extractor
configuration key `osii_tesseract_base_url`). The adapter posts the original
file to this endpoint; this service must not mount or write OSII's `.osii`
store.

## Why this is separate from Processor API v1

Processor API v1 uses JSON requests with explicit `request_id`, a descriptor,
and `/v1/extract`. This OCR service instead exposes its mature file-upload and
interactive OpenCV tuning API. That is intentional for now: it keeps the demo
and region controls useful as a standalone tool.

If this service is later made selectable through `OSII_PROCESSORS`, add a small
Processor API v1 wrapper that calls `/ocr/document` and translates its response.
Do not change the established OCR endpoint merely to satisfy the wrapper.
