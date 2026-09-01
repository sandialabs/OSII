# Tabular dataset Processor API example

This compact example demonstrates both levels of dataset processing without
adding a dataframe framework to OSII core:

- `demo.csv-table` extracts one CSV into grounded row segments and a standard
  table artifact.
- `demo.collection-table` combines compatible extracted rows across an OSII
  object, folder, collection, or root scope.

The distinction is intentional. Extraction says what one source contains. A
table across several independently grounded sources is a derived collection
product, so it is enrichment.

The easiest complete demo is:

```bash
make dev-datasets
```

On Windows PowerShell:

```powershell
.\scripts\osii.ps1 dev-datasets
```

This imports the bundled Purcell PDF plus Iris and Wine CSV datasets, starts
the normal application, and registers both example processors. Open
<http://localhost:5173/intake>, select `example-datasets`, and choose **CSV
dataset table extractor** for `.csv` files.

After Intake, open a CSV object's **Extractions** tab to inspect its source
table. To combine several CSVs, create a collection, open its **Derived
artifacts** section, select **Dataset collection table**, and run it. The
dashboard's standard table view is sortable and scrollable; it has no custom
knowledge of this example processor.

The services remain ordinary Processor API applications. Their independent
documentation is available at:

- extractor: <http://127.0.0.1:8097/docs>
- enricher: <http://127.0.0.1:8098/docs>

Subject-matter experts can copy `dataset_processors.py` into a separate
repository, replace the parsing logic, and retain the same typed requests,
descriptors, and standard table output.
