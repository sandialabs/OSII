# OSII processor modules integration - 2026-11-06

`banyan_extract.integrations.osii_extractor` exposes Banyan's Nemotron Parse
backend as an optional OSII Processor API v1 extractor. Its stable processor
ID is `banyan.nemotron-parse`. It accepts PDF, PNG, JPEG, and TIFF document
bytes, returning element text and normalized page bounding boxes. The OSII
adapter does not currently expose Banyan's standalone PPTX or LibreOffice
conversion workflows.

## Initialize and configure

In an OSII checkout this repository lives at `osii-processor-modules/banyan` as a
Git subtree. A normal OSII clone includes the source; no submodule initialization
is required.

Copy this tool's `.env.example` to `.env` in the same directory. On macOS/Linux:

```sh
cp osii-processor-modules/banyan/.env.example osii-processor-modules/banyan/.env
```

On Windows PowerShell:

```powershell
Copy-Item osii-processor-modules/banyan/.env.example osii-processor-modules/banyan/.env
```

Set `NEMOPARSE_ENDPOINT` to your approved Nemotron deployment's
OpenAI-compatible base URL, including its API prefix (usually `/v1`). Set
`NEMOPARSE_MODEL` to its served model identifier and `NEMOPARSE_API_KEY` if
authentication is required. These settings belong only to this service; do not
put credentials in OSII routes. Environment variables override the local file.
The adapter resolves `.env` relative to the Banyan checkout, regardless of the
directory from which you launch it.

## Run independently

From the OSII root, on macOS, Linux, or Windows, use Python 3.12 and the shared
`osii.processor_sdk` from this checkout:

```sh
uv run --no-project --python 3.12 --with-editable osii-core --with-editable "osii-processor-modules/banyan[nemotronparse,osii]" python -m uvicorn banyan_extract.integrations.osii_extractor:app --host 127.0.0.1 --port 8101
```

This creates an independent environment; no Banyan dependencies are added to
OSII's root workspace or lock. The normal local development stack starts the
service through `osii-processor-modules/banyan`, which owns the OSII host
environment. Set `OSII_START_PROCESSOR_MODULES=false` to leave Processor module services stopped,
and `OSII_BANYAN_PORT` to change the default port 8101. Starting the service
does not invoke a model. Health and descriptor discovery work without endpoint
access; extraction returns an actionable validation error until endpoint and
model are configured. Environment variables override Banyan's local `.env`.

In OSII Setup, select `banyan.nemotron-parse` for the desired PDF/image
extraction route, then test one document once Nemotron access is ready. The
service is discovered automatically by `make dev`; when running independently,
register its Processor API base URL `http://127.0.0.1:8101` in Setup. If OSII
runs on a different host, use a URL reachable from that host. The Nemotron
endpoint is separate from this Processor API URL. Extraction sends document
page images to the configured Nemotron deployment. Restart the service after
changing environment variables.

## API and provenance

- `GET /health`: service liveness, without contacting Nemotron.
- `GET /v1/descriptor`: supported formats and per-request settings.
- `POST /v1/extract`: OSII `ExtractionRequest` containing base64 source bytes.
  `model_name` and `sort_by_position` are optional request settings.
- `/docs`: generated request and response schemas.

The service uses only the supplied document bytes in an isolated temporary
directory, removed on both success and failure. It does not browse a library
or write OSII's canonical store. Each text-bearing element becomes a segment
whose `source_origin` retains the one-based page, element type, and normalized
`xmin`, `ymin`, `xmax`, and `ymax` coordinates. A `banyan_bounding_boxes` JSON
artifact preserves the complete returned element lists for page overlays.
Nemotron output is model-generated extraction, not authoritative source data.

## Offline validation

From the OSII root:

```sh
uv run --no-project --python 3.12 --with-editable osii-core --with-editable "osii-processor-modules/banyan[nemotronparse,osii]" --with pytest --with httpx python -m pytest osii-processor-modules/banyan/tests/unit/test_osii_extractor.py -q --api-test-mode=mock
```

The tests cover descriptor discovery, missing configuration, validation,
temporary file cleanup, provenance, and the HTTP-to-Banyan pipeline using
mocked Nemotron output. Live endpoint authentication and model compatibility
must be verified once endpoint access is available.
