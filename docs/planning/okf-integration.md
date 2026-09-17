# Future design note: Open Knowledge Format integration

> **Status: deferred proposal.** OSII does not currently read, write, or
> depend on Open Knowledge Format (OKF). This note records a possible
> interoperability direction for future work; it is not an implementation
> plan or a promise of compatibility.

## Why consider OKF

[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
is an emerging, human- and agent-readable knowledge-exchange convention. An
OKF bundle is a directory tree of Markdown files with YAML frontmatter. Its
design emphasizes portable knowledge, source provenance, generation and
verification identity, lifecycle, freshness, and optional attested
computations.

This complements OSII's purpose. OSII preserves the evidence-bearing,
inspectable intelligence layer around a corpus: unchanged source files,
canonical sidecars, extracted text, typed artifacts, explicit scopes, and
provenance. OKF could provide a readable, Git-friendly *knowledge view* over
that layer.

## Proposed boundary

If adopted, OKF must be an optional interchange and presentation layer, not a
replacement for OSII's canonical `.osii` store.

```text
Original files
    -> OSII sidecar (canonical evidence and provenance)
    -> optional OKF bundle (curated, portable knowledge view)
```

The OSII store remains responsible for source identity, extraction spans and
page locations, processor runs, scopes, access rules, and rebuildable search
indexes. OKF does not prescribe those operational concerns.

## Smallest useful first slice

The first feature should be a one-way, explicit collection export such as:

```text
osii export --format okf --scope collection --output <directory>
```

The generated bundle could contain:

- `index.md` with a navigable collection overview;
- Markdown concepts for selected objects and standard artifacts;
- source references that point back to stable OSII object and segment/page
  identifiers;
- frontmatter recording the generator, timestamp, source references, and
  derived/draft status.

Example OSII extension fields:

```yaml
---
type: osii:derived-summary
title: Results summary
osii_object_id: file-abc123
osii_artifact_id: synthesis-004
sources:
  - id: source-segment-19
    resource: osii://object/file-abc123/segment/seg-019
generated:
  by: osii/local-synthesizer
  at: 2026-09-02T14:00:00Z
status: draft
---
```

## Guardrails

- Generated text is derived material, never a replacement for source evidence.
- Every generated claim should preserve a resolvable OSII source reference.
- Human-authored Markdown and generated Markdown must remain distinguishable;
  regeneration must never overwrite a person's work.
- Exports must honor the selected scope and its access/sensitivity rules.
- Pin the emitted OKF version and validate generated bundles with fixtures.
- Keep OSII-specific keys namespaced or otherwise clearly documented so generic
  OKF consumers can ignore them safely.
- Use ordinary relative paths in OSII's MkDocs documentation. OKF's
  bundle-root path convention should be used only inside a deliberately
  exported OKF bundle, where an OKF-aware consumer resolves it.

## Possible later import path

After export has proved useful, OSII could import a human-authored OKF concept
as a versioned `wiki_markdown` or knowledge-note artifact. Import must retain
the original Markdown, author/revision identity, cited source references, and
review state. It must not silently alter canonical extraction outputs.

## Deliberate non-goals

- Do not rewrite `.osii` storage as Markdown or YAML.
- Do not make OKF a runtime dependency of core ingestion, search, or chat.
- Do not treat OKF's trust signals as OSII access control.
- Do not claim formal or universal standard status for OKF while it remains an
  emerging specification.

## Revisit trigger

Revisit this proposal when OSII needs to exchange a curated, evidence-linked
knowledge collection with another team or tool, or when Git-reviewable
human-and-agent authored knowledge becomes a concrete product requirement.
