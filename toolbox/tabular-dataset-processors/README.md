# OSII tabular dataset processors

Two optional, containerized OSII Processor API services for grounded tabular
data. Their source lives in `toolbox/` in the main OSII repository, separately
from Core's runtime dependencies: an organization may run them by default, replace
them with a domain-specific implementation, or leave them out entirely.

- `extractor` (`toolchest.csv-table`) reads one CSV file, returns a normal text
  segment for every row, and produces an OSII standard `table` artifact with
  row-level source-line provenance.
- `enricher` (`toolchest.collection-table`) combines compatible rows already
  extracted from an explicit OSII scope, retaining source-file and character
  provenance for every merged row.

Neither service reads an OSII directory or writes `.osii` storage. OSII Core
passes an explicit request, validates the typed result, and commits it.
See [the embedded Processor API contract](docs/OSII_PROCESSOR_API.md).

## Build one image

From the OSII repository root (see [deployment and Quay publishing](../README.md)):

```bash
podman build --format docker \
  -f toolbox/tabular-dataset-processors/Dockerfile \
  -t osii-tabular-dataset-processors:0.1.0 .
```

The image runs one service per container. Start both only when you want both
table extraction and collection enrichment:

```bash
podman run -d --name osii-csv-table-extractor -p 8097:8097 \
  osii-tabular-dataset-processors:0.1.0 extractor
podman run -d --name osii-collection-table-enricher -p 8098:8098 \
  osii-tabular-dataset-processors:0.1.0 enricher
```

For a developer running OSII on the same host, append both URLs to its `.env`
before starting the normal `make dev` stack:

```dotenv
OSII_PROCESSORS=http://127.0.0.1:8097,http://127.0.0.1:8098
```

In a Podman deployment, use the service's reachable host or container-network
address instead. Confirm each capability with `/health`, `/v1/descriptor`, or
`/docs` before configuring OSII.

## Development and tests

From the OSII root, these commands work in macOS/Linux and Windows PowerShell.
Each run uses an isolated uv environment rather than Core's environment:

```bash
uv run --no-project --python 3.11 --with-editable packages/osii-processor-sdk --with-editable toolbox/tabular-dataset-processors --with pytest python -m pytest toolbox/tabular-dataset-processors/tests -q
uv run --no-project --python 3.11 --with-editable packages/osii-processor-sdk --with-editable toolbox/tabular-dataset-processors python toolbox/tabular-dataset-processors/run.py extractor --host 127.0.0.1
```

The last command stays running. Start the enricher in a second terminal:

```bash
uv run --no-project --python 3.11 --with-editable packages/osii-processor-sdk --with-editable toolbox/tabular-dataset-processors python toolbox/tabular-dataset-processors/run.py enricher --host 127.0.0.1
```
