# Processor examples

These implementations are intentionally small and readable:

- `extractor.py`: source bytes to grounded text;
- `synthesizer.py`: scope text to cited Markdown;
- `embedder.py`: identified text to vectors;
- `enricher.py`: scope text to a standard entity-list artifact.

They demonstrate contracts, not production algorithms. Copy one into its own
service directory, add domain dependencies and tests, then containerize it in
the same pattern as `services/table-pdf-enricher`.

