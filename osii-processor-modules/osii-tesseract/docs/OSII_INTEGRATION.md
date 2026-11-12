# OSII integration contract

This service is a Processor API v1 extractor. OSII Core calls
`POST /v1/extract`, receives region-grounded OCR segments, and remains solely
responsible for canonical `.osii` persistence. The native OCR API remains for
interactive tuning and non-OSII consumers.

## Endpoint OSII calls

OSII calls `POST /v1/extract` with the standard JSON Processor API request.
The source file is `document.content_base64`; configuration includes OCR
language, confidence threshold, and selected OpenCV region-detection settings.
The response provides one `ocr_region` segment per retained OCR region.

Each segment's `source_origin` contains `page`, normalized `bbox`, normalized
`polygon`, `confidence`, `page_width`, and `page_height`.

## Native OCR endpoint

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

## Two complementary APIs

Processor API v1 is the stable OSII integration boundary. The native upload API
is deliberately retained because it makes the OpenCV tuning demo and direct OCR
experimentation useful without OSII. Both paths use the same region-detection
and OCR pipeline.
