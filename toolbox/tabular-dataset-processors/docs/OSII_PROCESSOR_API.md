# OSII Processor API contract

This image exposes one Processor API v1 capability per process. It never
browses an OSII source directory or writes OSII storage; Core validates and
persists the typed response.

| Service command | Default port | Descriptor | Operation |
| --- | ---: | --- | --- |
| `extractor` | 8097 | `toolchest.csv-table` | `POST /v1/extract` |
| `enricher` | 8098 | `toolchest.collection-table` | `POST /v1/enrich` |

Every process also provides `GET /health`, `GET /v1/descriptor`, and FastAPI
schema documentation at `GET /docs`. The exact request and response schemas
are supplied by the bundled `osii-processor-sdk`; inspect `/docs` on the
running service when integrating a particular release.

The extractor accepts CSV bytes as an explicit base64 document payload and
returns normal text segments plus the standard `table` artifact. The enricher
accepts an explicit OSII scope and combines JSON-line table rows from prior
CSV extraction, retaining a file reference and character span for every row.
