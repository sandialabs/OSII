# OSII processor API v1

OSII processors are small HTTP services. They are intentionally independent of
the OSII store: the core sends an explicit input and is the only service that
writes returned results into `.osii`.

Every service exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /v1/descriptor` | Identity, kind, capabilities, and configuration schema |

It then exposes exactly one operation:

| Kind | Operation |
|---|---|
| Extractor | `POST /v1/extract` |
| Synthesizer | `POST /v1/synthesize` |
| Embedder | `POST /v1/embed` |
| Enricher | `POST /v1/enrich` |

All payloads include `api_version: "v1"` and a caller-generated `request_id`.
Unknown fields are rejected where the SDK marks models as strict. Services must
return the same request ID.

Detailed contracts:

- [Extraction API](extraction.md)
- [Synthesis API](synthesis.md)
- [Embedding API](embedding.md)
- [Enrichment API](enrichment.md)
- [Standard artifact formats](standard-artifacts.md)

Copyable implementations live in `packages/osii-processor-sdk/examples`.
Start there when creating an independently deployable custom processor.

`config_schema` uses the ordinary JSON Schema object/property vocabulary. The
dashboard currently renders string fields (use `format: "textarea"` for long
prompts), numbers, integers, Booleans, and enums. Titles, descriptions,
defaults, and numeric bounds become labels, guidance, initial values, and form
constraints. These settings must be non-secret.

## Store and trust boundary

Processors must not receive a writable OSII volume. They may use bundled local
models, call an approved remote model, or implement deterministic domain logic.
The core controls selection, request limits, retries, provenance validation,
and committing results.

For intermittently connected environments, every required processor category
must have at least one configuration that runs without internet access after
its container image and model assets have been installed.
