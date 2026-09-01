# Demonstrate tabular datasets

OSII can ground and display structured data without turning core into a
dataframe application. A standard table is the portable, inspectable result
when a file or an explicit OSII scope has meaningful rows and columns. The
included example treats each CSV partition as a source object and a merged
dataset table as a derived product over an explicit scope.

## The table extraction pattern

Use a table extractor when one source file already contains a defensible table:
CSV, a laboratory export, a spreadsheet sheet, or a table recovered from a
document. The extractor returns typed columns, rows, and row-level provenance
alongside the normal extracted text. That makes the table visible in the file's
**Extractions** tab without making it a special dashboard feature.

Use a table enricher when the requested table spans an OSII scope. An object,
folder, collection, or the root scope can become one table when the operation
is explicitly about combining, filtering, or joining already-grounded rows.
The output is a rebuildable derived artifact, preserving a source reference for
every row. This is the boundary that keeps a table over many files honest and
repeatable.

Both forms use the same standard table artifact. People can scroll, sort, and
copy the displayed rows as CSV. The JSON table, typed columns, and provenance
are intentionally the future agent-facing contract: agents should be able to
read and act on the same artifact rather than requiring a separate CSV parser
or UI-specific integration.

## Start the complete example

On macOS or Linux:

```bash
make dev-datasets
```

On Windows PowerShell:

```powershell
.\scripts\osii.ps1 dev-datasets
```

The command performs two visible steps:

1. It copies the bundled Purcell PDF into `osii-data/source/example-documents`.
2. It exports the Iris and Wine datasets bundled with scikit-learn into
   temporary ZIP archives, then safely unpacks their CSV partitions and data
   cards beneath `osii-data/source/example-datasets`.

If `.env` sets `OSII_SOURCE_DIR`, the importer uses that directory instead so
the examples appear in the same Intake root as the running application.

No dataset content is fetched from the internet. Installing the scikit-learn
Python package may still require access to the configured package repository on
the first run.

To install the files without starting OSII, use `make demo-data` or
`.\scripts\osii.ps1 demo-data`.

## Process one source table

Open **Intake**, select an Iris or Wine `data` folder, and choose **CSV dataset
table extractor** for `.csv` files. The example extractor:

- reads the header and infers simple numeric or text column types;
- returns one JSON row segment grounded to each source CSV line;
- returns the same rows as a standard table artifact;
- does not call a model, mutate the source, or write `.osii` itself.

After processing, open a CSV object's **Extractions** tab and expand
**Extracted data products**. The dashboard renders the standard table with its
existing sortable, scrollable viewer. Use **Copy CSV** to put the currently
displayed row order on the clipboard. No CSV-specific dashboard component is
required.

## Combine partitions deliberately

Extraction describes one source. Combining the Setosa, Versicolor, and
Virginica CSV partitions is a new product over several sources, so it is an
enrichment rather than extraction.

Create an **Iris dataset** collection containing the three processed CSV
objects. Open **Derived artifacts**, expand **More available enrichment
methods**, select **Dataset collection table**, and generate the artifact. Each
merged row retains its source file and a character span in the grounded
extraction.

The same enricher also accepts folder and root scopes, but a collection is
usually the clearer choice when membership represents an intentional dataset
rather than the incidental layout of a drive.

## Copy the extension

The complete processor is
[`examples/tabular-dataset-processors/dataset_processors.py`](https://github.com/sandialabs/OSII/blob/main/examples/tabular-dataset-processors/dataset_processors.py).
It contains one extractor and one enricher built only against the public
Processor SDK. A subject-matter expert can copy it into an independent
repository, replace the CSV parser with a laboratory or domain parser, and
retain the same descriptors, typed requests, provenance, and standard table
output.

For direct Python use, continue with
[`11_Explore_tabular_datasets.py`](https://github.com/sandialabs/OSII/blob/main/osii-demo-notebooks/11_Explore_tabular_datasets.py).
