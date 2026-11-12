# OSII-Tesseract API Contract

This document defines the current HTTP API contract for OSII-Tesseract.

OSII-Tesseract performs OCR using:

- OpenCV for region detection
- Tesseract for OCR
- region-level deskew using rotated polygons when available

## General conventions

- Base URL is deployment-specific, for example:
  - `http://127.0.0.1:8081`
- All responses are JSON unless otherwise noted.
- Page numbers are 1-indexed.
- Confidence values are normalized to `0.0` to `1.0`.
- `polygon` points are ordered:
  - top-left
  - top-right
  - bottom-right
  - bottom-left

## Coordinate conventions

Current contract:

- `bbox` and `polygon` use normalized coordinates
- x coordinates are fractions of image width
- y coordinates are fractions of image height
- values are typically in the range `[0.0, 1.0]`
- origin is top-left
- x increases to the right
- y increases downward

When page-level responses include `width` and `height`, pixel coordinates can be reconstructed if needed.

## `POST /ocr`

Run OCR on a single image.

### Request

Content type:

```text
multipart/form-data
```

Fields:

- `file` required
  - image file
- `language` optional
  - ISO 639-1 language code
  - default: `en`

### Response

```json
{
  "results": [
    {
      "text": "recognized text",
      "bbox": [0.012, 0.041, 0.073, 0.058],
      "confidence": 0.95,
      "polygon": [
        [0.012, 0.041],
        [0.073, 0.041],
        [0.073, 0.058],
        [0.012, 0.058]
      ]
    }
  ]
}
```

### Notes

- This endpoint is image-only.
- OCR runs on detected text regions rather than the full page image.
- When rotated region geometry is available, a deskewed local crop is sent to Tesseract.

## `POST /ocr/document`

Run OCR on an image or PDF and return per-page results.

### Request

Content type:

```text
multipart/form-data
```

Fields:

- `file` required
  - image or PDF
- `language` optional
  - ISO 639-1 language code
  - default: `en`

### Response

```json
{
  "pages": [
    {
      "page": 1,
      "width": 1700,
      "height": 2200,
      "results": [
        {
          "text": "recognized text",
          "bbox": [0.012, 0.041, 0.073, 0.058],
          "confidence": 0.95,
          "polygon": [
            [0.012, 0.041],
            [0.073, 0.041],
            [0.073, 0.058],
            [0.012, 0.058]
          ]
        }
      ]
    }
  ]
}
```

### Notes

- `width` and `height` are returned in pixels.
- Region geometry in `results` is normalized to page width and height.
- Consumers that need pixel coordinates should multiply by `width` and `height`.

## Demo endpoints

These endpoints support the interactive tuning UI.

### `GET /demo`

Returns the demo HTML page.

### `GET /demo/config`

Returns the default detection and recognition parameters used to initialize the demo UI.

Example:

```json
{
  "defaults": {
    "detection": {
      "threshold_mode": "adaptive",
      "blur_kernel": 3,
      "adaptive_block_size": 31,
      "adaptive_c": 15,
      "open_kernel_w": 4,
      "open_kernel_h": 2,
      "dilate_kernel_w": 30,
      "dilate_kernel_h": 30,
      "dilate_iterations": 1,
      "min_contour_area": 50,
      "min_width": 10,
      "min_height": 8,
      "bbox_padding": 4,
      "max_regions": 200
    },
    "recognition": {
      "language": "en",
      "tesseract_psm": "auto",
      "confidence_threshold": 0.5
    }
  }
}
```

### `POST /demo/upload`

Upload a PDF or image for demo use.

Response includes:

- `doc_id`
- `page_count`
- per-page metadata and image URLs

### `POST /demo/detect`

Run OpenCV region detection only and cache the detected region set.

Request body:

```json
{
  "doc_id": "string",
  "page": 1,
  "params": {
    "threshold_mode": "adaptive",
    "blur_kernel": 3,
    "adaptive_block_size": 31,
    "adaptive_c": 15,
    "open_kernel_w": 4,
    "open_kernel_h": 2,
    "dilate_kernel_w": 30,
    "dilate_kernel_h": 30,
    "dilate_iterations": 1,
    "min_contour_area": 50,
    "min_width": 10,
    "min_height": 8,
    "bbox_padding": 4,
    "max_regions": 200
  }
}
```

Response includes:

- `region_set_id`
- debug image URLs
- detected regions
- detection stats

### `POST /demo/ocr`

Run OCR on a previously cached region set.

Request body:

```json
{
  "doc_id": "string",
  "page": 1,
  "region_set_id": "string",
  "detection_params": {
    "threshold_mode": "adaptive",
    "blur_kernel": 3,
    "adaptive_block_size": 31,
    "adaptive_c": 15,
    "open_kernel_w": 4,
    "open_kernel_h": 2,
    "dilate_kernel_w": 30,
    "dilate_kernel_h": 30,
    "dilate_iterations": 1,
    "min_contour_area": 50,
    "min_width": 10,
    "min_height": 8,
    "bbox_padding": 4,
    "max_regions": 200
  },
  "recognition_params": {
    "language": "en",
    "tesseract_psm": "auto",
    "confidence_threshold": 0.5
  }
}
```

Response includes:

- OCR results
- OCR overlay image URL
- OCR stats

## Tesseract PSM behavior

`recognition_params.tesseract_psm` supports:

- `"auto"`
- `"6"`
- `"7"`
- `"8"`
- `"11"`
- `"13"`

If `"auto"` is used, OSII-Tesseract chooses a mode heuristically based on the deskewed region crop shape.

## Error format

On error, endpoints return:

```json
{
  "error": "Description of the error"
}
```

with an appropriate HTTP status code such as:

- `400`
- `404`
- `500`

## Notes for downstream consumers

- Results are region-level OCR observations, not a fully reconstructed document reading order.
- Downstream grouping into lines or blocks may still be needed.
- `polygon` should be preferred when local rotation matters.
- `bbox` is the normalized axis-aligned envelope of the region.
- Confidence filtering may be applied by clients depending on use case.