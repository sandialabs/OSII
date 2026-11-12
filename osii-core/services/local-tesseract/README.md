# Baseline page-by-page Tesseract OCR

This Processor API extractor runs ordinary Tesseract over each complete PDF or
image page. It returns one text segment per page with word-level bounding boxes, exact
page-text character offsets, and optional normalized Tesseract confidence.

It is the dependable OCR path bundled in the `osii-baseline-processors` image.
That image contains the Tesseract executable and eight checked languages, so
the packaged stack needs no separate OCR image.

For bare-metal development, install Tesseract on the host before `make dev` or
`.\scripts\osii.ps1 dev`. OSII will start this Python service automatically.

This service intentionally has no OpenCV contour detection or region tuning.
Both OCR methods provide source geometry. The optional **Tesseract OCR with
OpenCV regions** processor in `osii-processor-modules/osii-tesseract` adds region detection
and tuning. View a saved OCR version with its original in the document’s Text
versions view; earlier page-only results need to be extracted again.

Endpoints: `/health`, `/v1/descriptor`, `/v1/extract`, `/docs`, `/redoc`, and
`/openapi.json`.

Geometry uses top-left normalized page coordinates (0–1). Confidence is a
method score, not a calibrated probability. Region character spans address the
reconstructed page text, not original PDF bytes. A page timeout fails the
extraction with an actionable error; isolated extraction staging preserves the
previous primary and the batch worker can continue with other documents.
