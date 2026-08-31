# Extraction versions and downstream lineage

OSII preserves extractor output as immutable versions. This makes it safe to
try a higher-quality extractor without concatenating text into an existing
object or losing the provenance of the earlier result.

## Dashboard workflow

**Intake** has three sections:

- **Add files** extracts new source files and can run selected downstream
  steps.
- **Process library** queues embeddings, summaries, enrichments, or an
  extraction upgrade without repeating unrelated work.
- **Activity** shows current and previous processing runs.

Use **Process library → Upgrade extraction** to choose a better extractor.
After extraction succeeds, choose one of these policies:

- **Make it primary and preserve the previous version** changes the text used
  by future processing. Existing downstream outputs are marked stale.
- **Save as another version** preserves both results and leaves the current
  primary extraction unchanged. Downstream work is not run against the new
  version until it becomes primary.

The **Extractions** tab on a document shows its versions, lets the user queue
that one original through any currently ready extractor, and allows a
preserved version to become primary. This tab queues extraction only. Summary
generation belongs to the separate **Syntheses** tab, while embeddings and
enrichments remain separate downstream operations.

## Store layout

```text
objects/<file-id>/
  meta.toml
  text.txt                         # compatibility mirror of primary text
  manifest.jsonl                  # compatibility mirror of primary manifest
  provenance.toml                 # compatibility mirror of primary provenance
  extractions/
    index.json                    # primary pointer and version summaries
    <extraction-id>/
      text.txt
      manifest.jsonl
      provenance.toml
      artifacts/
```

An extractor first writes into an isolated temporary OSII store. Core validates
and moves the completed bundle into `extractions/<extraction-id>/`; a failed
extractor cannot partially overwrite the current primary result. Existing
pre-versioning objects are registered as a `legacy-*` version the first time
they are read or reprocessed.

## Lineage and staleness

Syntheses and object enrichments record the primary extraction ID used as
input. Chunk manifests also record `source_extraction_id`. Embedding indexes
continue to be isolated by provider and model.

Changing the primary extraction marks search chunks, embeddings, syntheses,
and enrichments stale. The Process library planner counts stale outputs as work
that can be queued again. Previous files remain available for inspection until
an explicit future retention operation removes them.

## API

```http
GET /api/objects/{file_id}/extractions
POST /api/objects/{file_id}/extractions
POST /api/objects/{file_id}/extractions/{extraction_id}/primary
```

The document-level `POST` accepts `extractor_name` and an optional
`extraction_policy` (`make_primary` or `save_variant`). It resolves the
canonical original by its recorded path and hash, then sends one
extraction-only operation to the normal durable run queue. If the original was
moved or changed, rescan source paths before re-extracting it.

`POST /api/resolve` accepts the same operation fields as `POST /api/runs` and
returns `preview.processing_plan` with eligible, current, and blocked counts.
Processing runs accept:

- `workflow`: `intake` or `library`;
- `run_extraction`: boolean;
- `extract_mode`: `missing` or `reprocess`;
- `extraction_policy`: `make_primary` or `save_variant`;
- `synthesizer_name`;
- `build_embeddings`; and
- `enricher_name`.

For a downstream-only library run, documents without an extraction are shown
as blocked in the preview and skipped when the run is queued.
