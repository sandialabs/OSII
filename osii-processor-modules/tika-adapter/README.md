# Apache Tika processor module

General text extraction through Apache Tika, with a managed runtime included in
the normal `make dev` / PowerShell development startup. No separate Java or Tika
installation is needed. The first start installs the module's pinned Java package
and downloads Apache Tika 3.3.3 into the runtime cache after verifying its pinned
SHA-512 checksum. Later starts use the verified cache. Neither binary is committed
to Git. Downloads use the configured corporate certificate trust.

Set `OSII_ENABLE_TIKA=false` in the root `.env` to omit the entire module, including
dependency preparation and downloads. Set `OSII_TIKA_MANAGED=false` to run the
adapter with an external Tika server instead; enter that server's address in
**Setup → Extractors → Apache Tika → Apache Tika endpoint**.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OSII_TIKA_ADAPTER_PORT` | `8102` | OSII Processor API |
| `OSII_TIKA_SERVER_PORT` | `9998` | Managed Apache Tika on loopback |
| `OSII_TIKA_MANAGED` | `true` | Start/stop the managed JVM with this module |
| `OSII_TIKA_CACHE_DIR` | `<runtime>/processor-cache/tika` | Verified jar cache; can be prepopulated offline |

For independent startup, from this directory:

```sh
uv run python -m uvicorn tika_adapter.main:app --host 127.0.0.1 --port 8102
```

`GET /health` checks the adapter. `GET /upstream-health?tika_endpoint=...` checks
Apache Tika. Managed preparation errors are logged without stopping other
processors. A port conflict never causes OSII to adopt or stop another JVM.
Ctrl+C stops the owned JVM; the cache survives restart. First-start readiness can
briefly show unavailable while the download/JVM startup completes.

`POST /v1/extract` accepts document bytes, `config.tika_endpoint` (default managed
loopback endpoint), and `chunk_chars` (default 4000). Existing `tika` and
`tika_catchall` routes remain supported. The module never browses the corpus or
writes canonical data. Returned offsets refer to extracted text, not original
file bytes; PDF page boxes are not inferred.

Apache Tika is Apache-2.0 licensed. The pinned `jdk4py` package includes its Java
runtime and notices; supported wheels cover macOS Intel/Apple Silicon, Linux
x86-64/ARM64, and Windows x86-64. Other platforms need a supported runtime package.
See [Apache releases](https://tika.apache.org/download.html),
[routing](../../docs/reference/extractor-routing.md), and the
[extraction API](../../docs/reference/processor-api/extraction.md).

Tests: `uv run --extra dev pytest tests -q`.
