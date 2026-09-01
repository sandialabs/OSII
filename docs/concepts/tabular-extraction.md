# Tables and tabular extraction

An OSII table is a grounded, typed view of information that a person can
inspect now and an agent can use later. It is not a second database and it is
not a special dashboard widget for one processor. It is a standard artifact
with columns, rows, and provenance.

## Choose the right operation

| Starting point | OSII operation | Result |
| --- | --- | --- |
| One file has a recoverable table | Extractor | A source-derived table alongside canonical text and segments |
| One object needs a calculated or filtered table | Enricher | A rebuildable table artifact for that object |
| A folder, collection, or root needs rows combined across files | Enricher | A rebuildable scope table with row-level source references |

The distinction protects provenance. An extractor reports what one original
file contains. A table that combines several files is a new product over a
declared scope, so it is an enrichment.

## What people can do

OSII renders every standard table in the same small, predictable view:

- scroll rows in place;
- sort by a column; and
- choose visible columns with **Columns**; and
- use **Copy CSV** to copy the currently displayed row order and columns.

`Source File` is hidden at first so wide tables are easier to scan. It remains
available from **Columns** whenever provenance is needed.

Tables from an extractor appear under a file's **Extractions** tab. Tables from
an enricher appear under **Derived artifacts** for the selected object, folder,
collection, or root scope.

## What processors provide

A standard table provides a title, optional description, typed columns, rows,
and optional row provenance. The stable JSON is consumed by the dashboard now;
it is also the planned interface for agents to inspect a table, choose rows,
and follow rows back to source segments or character spans. Processor authors
should populate the narrowest provenance available and should not make an agent
depend on a processor-specific CSV format.

See [Standard enrichment artifact formats](../reference/processor-api/standard-artifacts.md)
for the field contract, or [Demonstrate tabular datasets](../tutorials/tabular-datasets.md)
for the CSV example.
