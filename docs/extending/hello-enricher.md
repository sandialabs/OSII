# Tutorial: build a hello enricher

This tutorial starts with the SDK's small enricher example and demonstrates the
complete extension loop. Copy it into a new repository, then replace its
placeholder logic with domain-specific behavior.

## What you will build

The service exposes:

- `GET /health`;
- `GET /v1/descriptor`;
- `POST /v1/enrich`.

Its implementation starts at
`packages/osii-processor-sdk/examples/enricher.py`. The important shape is:

```python
class DomainEnricher(Enricher):
    descriptor = ProcessorDescriptor(
        name="example.domain-enricher",
        version="0.1.0",
        display_name="Example Domain Enricher",
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

`create_processor_app(DomainEnricher())` supplies the FastAPI application and
all three endpoints.

## 1. Run the contract tests

From the repository root:

```bash
uv sync --package osii-processor-sdk --extra dev
uv run --package osii-processor-sdk pytest packages/osii-processor-sdk/tests
```

These tests validate strict model behavior. Add processor-specific tests beside
your copied service using representative input and expected table rows.

## 2. Create and run your service

Put a text file containing pipe-delimited data in `osii-data/source`, for
example:

```text
sample | temperature_c | pressure_kpa
A-101 | 22.4 | 101.2
A-102 | 24.1 | 100.8
```

Copy the SDK example into its own service repository, add its package metadata
and a small FastAPI entry point using `create_processor_app`, then build its
container. The example is intentionally not an OSII-managed container: it is
your service, with its own repository and release cycle.

Start OSII separately:

```bash
make run
```

## 3. Register and test the processor

1. Open <http://localhost:5173/admin/processors>.
2. Enter an ID such as `my-domain-enricher`.
3. Enter your service's display name.
4. Select kind `enricher`.
5. Enter its reachable base URL.
6. Select **Add processor**.
7. Select **Health**, then **Test**. Both should pass.

When both OSII and the processor run in containers, use the processor's
container-network URL rather than `localhost`: the OSII API calls it from a
different container.

## 4. Produce and view the artifact

1. Open **Intake**, choose a broad folder or the sample file, and start intake.
2. Open the resulting file in the dashboard.
3. In the file action area, choose your enricher and run enrichment.
4. Open the **Enrichments** tab.

The table appears without custom frontend code because it uses
`TableArtifactData`. The same JSON is available to agents through the
enrichment artifact APIs.

## 5. Finish the processor

In its own repository:

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
