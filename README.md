# OSII coding documentation assistant

`osii-mcp` connects coding harnesses to an OSII library of PDF manuals, legacy
software documentation, research reports, and other reference material. It
combines source retrieval with a persistent, cited wiki that the harness can
improve while solving coding tasks. OSII remains the ingestion, search and
storage foundation; original evidence stays authoritative.

## Tools and workflow

| Tool | Purpose |
| --- | --- |
| `search_documentation` | Search current wiki knowledge first, falling back to scoped source passages. |
| `get_documentation_evidence` | Read a bounded canonical passage, source identity and available PDF page/segment origins. |
| `list_wiki_pages` | Discover wiki excerpts, applicability, revisions and freshness. |
| `get_wiki_page` | Read a saved harness page and its revision. |
| `save_wiki_page` | Create or revise source-cited knowledge through OSII Core. |

Existing scope, collection, object, text, search and enrichment tools remain
compatible. Collections can group documentation by software, version, project,
or experimental context. Documentation tools accept the same explicit scopes:
`{"scope_type":"collection","collection_id":"…"}`, folder scopes with
`folder_id`, object scopes with `file_id`, and `{"scope_type":"root"}`.
Omitting scope selects the root.

1. Ingest the reference files through the normal OSII workflow. Scanned PDFs
   require a configured OCR extractor. This MCP reads ingested material; it does
   not fetch or extract PDFs independently.
2. Call `search_documentation` with a question or symbol names, the appropriate
   scope, and known `software` / `software_version` context. Read matched wiki
   pages. Matching uses heuristic token coverage, so check that the page answers
   the actual question. Set `prefer_wiki=false` to always retrieve sources.
3. Inspect source passages with `get_documentation_evidence`. Use its canonical
   offsets for citations; preferred or edited text has separate coordinates.
4. Save useful conclusions as a focused wiki page. The harness's LLM authors
   the synthesis, using `knowledge_kind` to distinguish software documentation,
   experimental lessons, research findings, and other knowledge. Include
   conditions, limitations, conflicting findings and coding implications.
5. On later tasks, reuse applicable current pages. Revisit source evidence and
   revise pages when new experiments, contradictions or changed documentation
   alter the conclusion. Updates require the last read `expected_revision`;
   reread and reconcile on conflict.

The loop is harness-driven: the server supplies retrieval, persistence and
freshness checks, while the connected LLM decides what to learn and revise.
No background model invocation or additional model provider is required.

A `save_wiki_page` request has this shape (IDs and offsets must come from your
library's evidence):

```json
{
  "page_id": "producer-consumer-queues",
  "expected_revision": 0,
  "scope": {"scope_type": "collection", "collection_id": "project-docs"},
  "page": {
    "title": "Producer/consumer queue guidance",
    "markdown": "Summarize the source-backed behavior, constraints and coding implications here.",
    "knowledge_kind": "software_documentation",
    "software": "LabVIEW",
    "software_version": "version verified in the source",
    "tags": ["queues", "producer-consumer"],
    "citations": [{"file_id": "manual-file-id", "char_start": 100, "char_end": 250}],
    "change_summary": "Capture documented queue behavior and constraints"
  }
}
```

## Run with a coding harness

From the OSII monorepo root, install/run the workspace package with `uv`:

```bash
OSII_ROOT=/absolute/path/to/.osii uv run --package osii-mcp osii-mcp --stdio
```

Windows PowerShell:

```powershell
$env:OSII_ROOT="C:\path\to\.osii"
uv run --package osii-mcp osii-mcp --stdio
```

Configure a local harness's MCP command as `uv` with arguments
`["run", "--directory", "/absolute/path/to/osii", "--package", "osii-mcp", "osii-mcp", "--stdio"]`
and an `OSII_ROOT` environment value pointing to the processed library. STDIO
does not require a bearer token and reserves stdout for MCP protocol messages.
When installed independently, the command is `osii-mcp --stdio`; the installed
`osii` package must also be available.

For HTTP, retain the existing bearer-token configuration:

```bash
OSII_ROOT=/absolute/path/to/.osii ATLAS_MCP_TOKEN=replace-me uv run --package osii-mcp osii-mcp
```

```powershell
$env:OSII_ROOT="C:\path\to\.osii"
$env:ATLAS_MCP_TOKEN="replace-me"
uv run --package osii-mcp osii-mcp
```

The standalone default is `http://127.0.0.1:8021/mcp`; `MCP_HOST` and `MCP_PORT`
override it. `DEBUG=true` retains the existing development authentication bypass.
The host `make dev` workflow starts MCP on port 8022. Restart that terminal
after upgrading. Wiki saving requires write access to the OSII store and writes
only derived wiki artifacts. Compose deployment is archived.

## Storage, freshness and limits

Core stores pages as standard `wiki_markdown` JSON artifacts in their scope's
`enrichments/` directory, named `wiki_markdown--coding-assistant-<page_id>.json`.
Companion `.meta.json` files hold applicability, source fingerprints, revision,
change summary, and the latest 20 previous revisions. Payloads and metadata
are atomically replaced, with checksums connecting both generations. Concurrent
writers fail with a revision conflict or a busy-page error instead of silently
overwriting another contribution. A process killed while holding a page lock
may leave `.<filename>.lock`; remove that empty directory only after verifying
no writer is active, then reread the page before retrying.

Search visits the selected scope, its member documents, and root pages whose
citations all belong to the selected scope. Root search also visits folder and
collection wikis. Existing processor wiki artifacts remain readable; pages
without matching fingerprints are `untracked` and never suppress source search.

`current` means source identity, canonical text and segment manifest match the
saved snapshots. Changed or missing evidence is `stale`; refreshing requires
reading the new evidence and submitting a revised page. Changes to scope
membership also affect reuse. OSII must ingest upstream changes before the MCP
can detect them. Wiki matching is lexical, not semantic; software/version filters
on wiki metadata are exact case-insensitive matches. For source retrieval those
values expand the query, so actual software/version applicability still needs
source inspection. Source results report the retrieval mode actually used,
including OSII's lexical fallback for hybrid search without semantic results.

Pages are marked unreviewed. Validation checks citation bounds and scope
membership, not whether a claim is supported. The harness must distinguish
documented guarantees, experimental observations and inferred guidance, and
handle contradictions explicitly. Evidence reads are limited to 12,000
characters plus up to 2,000 context characters on either side. Search results
return wiki excerpts of at most 2,000 characters; `get_wiki_page` reads the full
page. Set `include_history=true` to inspect previous revisions; history is
omitted by default to save the harness's context. Page text is limited to
60,000 characters and at most 50 citations.

## Verify

```bash
uv run --package osii-mcp --extra dev python -m pytest osii-mcp/tests osii-core/tests/test_documentation_wiki.py -q
```

The tests include a real STDIO MCP client that reads evidence, saves a page,
reuses it without a source search, and verifies revision-conflict handling.
