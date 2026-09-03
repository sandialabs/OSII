# OSII-Tesseract

OSII-Tesseract is an OCR service built around:

- OpenCV for text-region detection
- Tesseract for OCR
- PyMuPDF for PDF rendering
- FastAPI for the API and demo UI

It supports:

- image OCR through a simple HTTP API
- per-document OCR for PDFs and images
- a demo UI for tuning OpenCV region-detection parameters before running OCR

This is an independently deployable OSII extractor. It exposes the generic OSII
Processor API v1 at `POST /v1/extract`, returning one OCR text segment per
detected region with normalized page bounding boxes and polygons. Its native
`/ocr/document` API and tuning UI remain available for direct inspection.

## Highlights

- Detect text regions first, then run OCR
- Region-level deskew using rotated rectangles
- Optional confidence filtering on OCR output
- Configurable Tesseract PSM
- Demo workflow for tuning morphology and contour filtering

## Demo screenshots

![Parameter tuning demo](docs/screenshots/demo_utility.png)
![Bounding boxes of text regions](docs/screenshots/ocr_bboxes.png)


## API

### `POST /v1/extract` — OSII Processor API v1

OSII sends a JSON request containing base64 source bytes. The service returns
one `ocr_region` segment per accepted region. Each segment's `source_origin`
contains the page number, normalized `bbox`, normalized `polygon`, confidence,
and original page dimensions. Use `GET /v1/descriptor` to discover the
supported file types and tunable OCR configuration; use `/docs` for the exact
schema.

### `POST /ocr`

OCR for a single image.

Request:

- content type: `multipart/form-data`
- fields:
  - `file`: image file
  - `language`: optional ISO 639-1 language code, default `en`

Response:

```json
{
  "results": [
    {
      "text": "recognized text",
      "bbox": [10, 20, 60, 40],
      "confidence": 0.95,
      "polygon": [[10, 20], [60, 20], [60, 40], [10, 40]]
    }
  ]
}
```

### `POST /ocr/document`

Per-document OCR for an image or PDF.

Request:

- content type: `multipart/form-data`
- fields:
  - `file`: image or PDF
  - `language`: optional ISO 639-1 language code, default `en`

Response:

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
          "bbox": [10, 20, 60, 40],
          "confidence": 0.95,
          "polygon": [[10, 20], [60, 20], [60, 40], [10, 40]]
        }
      ]
    }
  ]
}
```

### `GET /demo`

Interactive demo and tuning UI.

Use it to:

- upload a PDF or image
- select a page
- tune OpenCV preprocessing and contour filters
- inspect intermediate images
- detect regions before OCR
- run OCR on cached region sets
- filter OCR results by confidence

### `GET /health`

Returns `{"status": "ok"}` for host and container readiness checks.

## OCR pipeline

Per page, OSII-Tesseract:

1. loads the image or renders the PDF page
2. converts to grayscale
3. thresholds to suppress scan artifacts and faint stray marks
4. removes small noise with morphology
5. dilates to merge text into larger blobs
6. finds contiguous candidate regions
7. filters small or implausible regions
8. computes rotated rectangles and polygons
9. deskews each region locally
10. runs Tesseract on the deskewed region crop

PDF pages are rendered and recognized sequentially, keeping memory use bounded
for long documents instead of retaining every high-resolution page image.

## Local development

Install the native Tesseract executable first and confirm `tesseract --version`
works. From the OSII root, use an isolated Python 3.11 environment on macOS,
Linux, or Windows (Python 3.12 is also supported):

```sh
uv run --no-project --python 3.11 --with-editable packages/osii-processor-sdk --with-editable toolbox/osii-tesseract python -m uvicorn app.main:app --app-dir toolbox/osii-tesseract --host 127.0.0.1 --port 8080
```

Build the image from the OSII repository root. It includes Tesseract, so the
container path does not need a host installation. See [Quay publishing](../README.md).

```bash
podman build --format docker -f toolbox/osii-tesseract/Dockerfile -t osii-tesseract .
podman run --rm -p 8080:8080 osii-tesseract
```

Open:

```text
http://127.0.0.1:8080/docs
http://127.0.0.1:8080/demo
```

Contract tests (mocked OCR; no model downloads) run from this component directory:

```sh
uv run --no-project --python 3.11 --with-editable ../../packages/osii-processor-sdk --with-editable . --with pytest python -m pytest tests -q
```

## Configuration

Environment variables:

- `ENABLE_DEMO`
  - enables the demo UI
- `DEFAULT_PDF_DPI`
  - PDF render DPI
- `DEMO_STORAGE_DIR`
  - temporary storage used by the demo
- `DEMO_MAX_FILE_SIZE_MB`
  - demo upload size limit

## Notes

- `/ocr` is the strict image OCR endpoint.
- `/ocr/document` is the per-document extension endpoint.
- the demo module is optional and intended for parameter exploration and tuning.

## Troubleshooting

### OCR is very slow

This usually means the current OpenCV settings are producing too many candidate regions. Use the demo to tune:

- dilation kernel size
- morphology kernel sizes
- contour filtering thresholds
- max region cap

### Tiny stray marks are being treated as text

Tune:

- opening kernel size
- minimum contour area
- minimum width and height

### PyMuPDF fails to install locally

Use Python 3.12 for local Windows development.
