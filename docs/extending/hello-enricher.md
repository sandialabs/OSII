# Tutorial: build a hello table enricher

This tutorial uses the included table enricher to demonstrate the complete
extension loop. The processor reads pipe-delimited lines and returns a standard
table artifact. Replace its small parser with your own domain logic later.

## What you will build

The service exposes:

- `GET /health`;
- `GET /v1/descriptor`;
- `POST /v1/enrich`.

Its implementation is
`services/table-pdf-enricher/app/main.py`. The important shape is:

```python
class TablePdfEnricher(Enricher):
    descriptor = ProcessorDescriptor(
        name="example.table-pdf",
        version="0.1.0",
        display_name="Example Table PDF Enricher",
        kind=ProcessorKind.ENRICHER,
        # capabilities and configuration schema omitted here
    )

    def enrich(self, request: EnrichmentRequest) -> EnrichmentResponse:
        rows = parse_my_domain_table(request.scope.documents[0].text)
        return EnrichmentResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            artifacts=[
                Artifact(
                    id="table-rows",
                    kind="table_rows",
                    media_type="application/json",
                    standard_data=TableArtifactData(
                        title="Extracted table rows",
                        columns=[...],
                        rows=rows,
                    ),
                )
            ],
        )
```

`create_processor_app(TablePdfEnricher())` supplies the FastAPI application and
all three endpoints.

## 1. Run the contract tests

From the repository root:

```bash
uv sync --package osii-processor-sdk --extra dev
uv run --package osii-processor-sdk pytest packages/osii-processor-sdk/tests
```

These tests validate strict model behavior. Add processor-specific tests beside
your copied service using representative input and expected table rows.

## 2. Start OSII and the example

Put a text file containing pipe-delimited data in `osii-data/source`, for
example:

```text
sample | temperature_c | pressure_kpa
A-101 | 22.4 | 101.2
A-102 | 24.1 | 100.8
```

Start the required services:

```bash
docker compose --profile examples --profile chat --profile ocr up --build \
  api worker dashboard chat tika tesseract table-pdf-enricher
```

Podman users can replace `docker compose` with `podman compose`.

## 3. Register and test the processor

1. Open <http://localhost:5173/admin/processors>.
2. Enter ID `example-table-pdf`.
3. Enter display name `Example Table PDF Enricher`.
4. Select kind `enricher`.
5. Enter base URL `http://table-pdf-enricher:8091`.
6. Select **Add processor**.
7. Select **Health**, then **Test**. Both should pass.

Use the container-network URL above, not `localhost`: the OSII API calls the
processor from another container.

## 4. Produce and view the artifact

1. Open **Intake**, choose a broad folder or the sample file, and start intake.
2. Open the resulting file in the dashboard.
3. In the file action area, choose `example.table-pdf` and run enrichment.
4. Open the **Enrichments** tab.

The table appears without custom frontend code because it uses
`TableArtifactData`. The same JSON is available to agents through the
enrichment artifact APIs.

## 5. Turn the example into your processor

Copy `services/table-pdf-enricher` to a new service directory, then:

1. rename the package, class, and descriptor;
2. replace only the parsing logic first;
3. declare accepted media and scope types;
4. define a strict JSON configuration schema;
5. populate row provenance whenever the input supports defensible locations;
6. add golden tests;
7. add the service to Compose or deploy it at another reachable URL.

Choose one of the four
[standard artifact formats](../reference/processor-api/standard-artifacts.md)
so the dashboard and agents understand the result automatically.
