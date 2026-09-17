# Baseline page-by-page Tesseract OCR

This Processor API extractor runs ordinary Tesseract over each complete PDF or
image page. It returns one text segment per page with page-level provenance.

It is the dependable OCR path bundled in the `osii-baseline-processors` image.
That image contains the Tesseract executable and eight checked languages, so
the packaged stack needs no separate OCR image.

For bare-metal development, install Tesseract on the host before `make dev` or
`.\scripts\osii.ps1 dev`. OSII will start this Python service automatically.

This service intentionally has no OpenCV contour detection or region tuning.
The optional **Tesseract OCR with OpenCV regions** processor remains in
`osii-toolbox/osii-tesseract` for experiments that need bounding boxes.

Endpoints: `/health`, `/v1/descriptor`, `/v1/extract`, `/docs`, `/redoc`, and
`/openapi.json`.
