# Table PDF enricher example

This is a deliberately small reference processor for subject-matter experts. It
accepts document text over the OSII processor API and returns structured table
rows. It never mounts or writes the OSII store.

To make a custom processor:

1. copy this directory;
2. replace `TablePdfEnricher.enrich` with domain-specific logic;
3. update the descriptor and JSON configuration schema;
4. build the container;
5. add its URL to `OSII_PROCESSORS`.

The example splits pipe-delimited rows only. A real processor can use PDF
coordinates, a specialist parser, OCR, schemas, or validation rules. Binary
input is supplied as base64 when a processor requires the source file.
