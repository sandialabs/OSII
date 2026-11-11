# Apache Tika adapter for OSII

A small Processor API service connecting OSII to your own Apache Tika server.
It accepts one document's bytes and returns plain text chunks with extracted-text
character offsets. Core owns persistence; this service never browses your library.
Apache Tika is neither bundled nor automatically installed, downloaded, or started.

`make dev` starts this wrapper with the other optional toolbox services. Configure
**Setup → Extractors → Apache Tika → Apache Tika endpoint** and save. Existing
`tika` and `tika_catchall` routing identifiers continue working.

For independent deployment, from this directory:

```sh
uv sync
uv run python -m uvicorn tika_adapter.main:app --host 127.0.0.1 --port 8102
```

`GET /health` checks the wrapper. `GET /upstream-health?tika_endpoint=...` checks
an existing Apache Tika server's `/version`. `POST /v1/extract` forwards the
selected document bytes to that server's `/tika` endpoint. Requests specify
`config.tika_endpoint` (default `http://127.0.0.1:9998`) and optional `chunk_chars`
(default 4000). HTTP errors and connection failures return readable API errors;
no canonical data is written by this service. Credentials embedded in URLs are
rejected. Use a network-accessible trusted endpoint.

See [routing and configuration](../../docs/reference/extractor-routing.md) and
the [extraction API](../../docs/reference/processor-api/extraction.md).

Tests: `uv run --extra dev pytest tests -q`.
