# Local native-text extractor

Processor API v1 service `local.native-text`. Run from the monorepo with
`make dev`, then open <http://localhost:8092/docs>. It accepts source
bytes at `POST /v1/extract` and returns grounded segments. Text-layer PDFs,
DOCX, PPTX, XLSX, RTF, and common text/data formats are supported; scanned PDFs
return a clear warning that an OCR processor is required.
