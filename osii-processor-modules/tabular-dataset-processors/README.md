# OSII tabular dataset processors

Two optional, Python OSII Processor API services for grounded tabular
data. Their source lives in `osii-processor-modules/` in the main OSII repository, separately
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

## Development and tests

From the OSII root, these commands work in macOS/Linux and Windows PowerShell.
Each run uses an isolated uv environment rather than Core's environment:

```bash
uv run --no-project --python 3.12 --with-editable osii-core --with-editable osii-processor-modules/tabular-dataset-processors --with pytest python -m pytest osii-processor-modules/tabular-dataset-processors/tests -q
uv run --no-project --python 3.12 --with-editable osii-core --with-editable osii-processor-modules/tabular-dataset-processors python osii-processor-modules/tabular-dataset-processors/run.py extractor --host 127.0.0.1
```

The last command stays running. Start the enricher in a second terminal:

```bash
uv run --no-project --python 3.12 --with-editable osii-core --with-editable osii-processor-modules/tabular-dataset-processors python osii-processor-modules/tabular-dataset-processors/run.py enricher --host 127.0.0.1
```
