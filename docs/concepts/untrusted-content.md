# Untrusted content and prompt injection

OSII reads files a person did not write, sends their text to a language model,
and stores the result as durable knowledge that later stages treat as true.
That pipeline has a trust boundary in it, and this page describes where the
boundary sits, how it can be crossed, and the design OSII uses to hold it.

This is a design document. It records the intended behavior and the reasoning
behind it so that the hardening work is reviewable before it lands.

## The trust boundary

Prompt injection is usually described as a user typing a jailbreak into a chat
box. That is not the shape of the problem here. OSII's exposure is *indirect*:
a document in the corpus contains text addressed to the model rather than to a
reader, and OSII processes it without a human in the loop.

| Input | Trust | Why |
|---|---|---|
| Source files under `osii-data/source` | Untrusted | Arbitrary content from arbitrary origins |
| Filenames and folder names | Untrusted | Chosen by whoever supplied the files |
| Extracted text and OCR output | Untrusted | Faithful reproduction of untrusted input |
| Expert context | Trusted | Supplied by an operator on the command line or in Intake |
| Prompt templates under `synthesis/*/prompts/` | Trusted | Part of the repository |
| Synthesis, wiki pages, entity records | **Derived** | Trusted by later stages, but computed from untrusted input |

The last row is the one that matters. A derived product is only as trustworthy
as the boundary that produced it. If untrusted text can influence what a
synthesizer writes, then the synthesis carries that influence forward with the
authority of an OSII artifact — into folder overviews, into the wiki, into
retrieval evidence, into chat answers, and out through the MCP server to agents
that may hold far more capability than OSII does.

!!! note "Expert context is the one channel with real authority"
    `expert_context` is interpolated under a "GUIDANCE (follow closely)"
    heading and is meant to be obeyed. It must stay operator-supplied. No
    file-derived text may ever populate it, in any processor, for any reason.

## Where untrusted text reaches a model today

| Surface | Entry point | Untrusted values |
|---|---|---|
| Object description | `synthesis/file/describe.py` | extracted text, file metadata |
| Recursive synthesis | `synthesis/file/recursive.py` | chunk text, then stage-one output |
| Folder description | `synthesis/folder/describe.py` | folder overview, filenames |
| Image description | `synthesis/file/image_describe.py` | metadata, prior synthesis |
| Wiki auto-integration | `enrichment/auto_integrate.py` | source page text, candidate evidence |
| Dashboard chat | `domain/services/chat.py` | retrieved snippets, scope synthesis |
| RAG chat service | `ai-ready-rag-chat/app/prompts.py` | retrieved snippets, scope |
| MCP tools | `ai-ready-mcp/osii_mcp/main.py` | every corpus-derived field returned |

Two structural weaknesses run through all of them.

**The fence is guessable.** Extracted text is delimited with a literal `"""`
in `object_describe_user.txt` and the recursive chunk prompt. A document that
contains `"""` closes the fence, and everything after it reaches the model in
the same position as OSII's own instructions.

**The system prompts carry no defense.** Each is a single sentence about being
careful and uncertainty-aware. Nothing states that document content is data to
be described rather than instruction to be followed, so the model has no stated
rule to fall back on when the document claims otherwise.

A third weakness is specific to recursive synthesis: stage one summarizes
chunks, stage two consolidates those summaries. Text that survives stage one
arrives at stage two labelled `INPUT SYNTHESIS` — untrusted content promoted to
trusted-looking content by nothing more than passing through a model once.

## First hardening target: wiki auto-integration

The wiki integrator is the highest-consequence surface and the first one OSII
will harden. Synthesis produces a description that a person reads and can
disbelieve. Auto-integration produces *files* — entity pages, concept pages,
aliases, grounding bullets — that persist, that the dashboard renders, that
retrieval indexes, and that no one re-reads against the source.

### What can go wrong

**Instruction hijack.** In `auto_integrate.py` the source page is interpolated
into the user message with no delimiter of any kind, immediately after roughly
sixty lines of extraction rules. A document that mimics that register can
plausibly add rules of its own: extract this entity, use these aliases, apply
this summary. The result is a durable wiki page asserting whatever the document
asked for, carrying OSII's provenance formatting.

**Structural forgery in page bodies.** `_clean_string` is `str(value).strip()`
and nothing more. Model-supplied `name`, `summary`, and `evidence` are written
verbatim into markdown page bodies. YAML frontmatter is safe — it goes through
`yaml_string`, which is `json.dumps` — but the body is not, and the body is
parsed again on the next run. Two consequences follow:

- A `summary` containing a `## Source grounding` heading creates a second
  section. `ensure_source_grounding_bullet` matches with
  `(^## Source grounding\s*\n)(.*?)(?=^## |\Z)` and will then append later
  provenance into whichever section it finds first.
- That function skips its work entirely when `source_link in page_text`. A
  summary that embeds a `[[path]]` link matching a future source suppresses the
  real grounding bullet for that source permanently. Injected content can
  decide which documents the wiki admits as evidence.

The second one is the more serious. It is not a crash or a bad summary; it is a
silent, durable subversion of the provenance record that OSII's value rests on.

**Rendering.** Entity and wiki pages are displayed through `react-markdown` in
`EntityPageBrowser.tsx`, `WikiBundleBrowser.tsx`, and `EnrichmentArtifactView.tsx`
without `rehype-raw`, so raw HTML is not rendered and there is no script
execution path. Markdown images are still rendered, so a page body containing
an external image reference issues an outbound request when a person opens it,
with whatever the model was induced to place in the URL.

### What is already sound

Worth stating plainly, so the hardening does not re-solve solved problems:

- `entity_type` is normalized against `ALLOWED_ENTITY_TYPES`, so the taxonomy
  is closed and a model cannot invent a type.
- `slugify` strips path separators and trims leading and trailing `-._`, so
  `..` collapses to the fallback. Directory traversal through entity or concept
  names is not reachable.
- Frontmatter is JSON-escaped.
- Existing pages carrying `manual_edit_utc` are skipped, so a person's edits
  are not overwritten by a later run.
- Malformed JSON is retried once and then raises, rather than being coerced.

The residual filename issue is small and separate: `concept_page_path` produces
`concepts/<namespace>/<name>.md` with no prefix, so a concept named `CON`,
`NUL`, or `AUX` yields a Windows reserved device name. Windows is the primary
deployment platform, and the extension does not exempt it.

### The design

Five changes, ordered by how much they carry. Steps 1 to 4 are implemented in
`enrichment/auto_integrate.py`; step 5 is not yet built.

**1. Fence the source page with a per-call nonce.** A single helper generates a
random token per model call and wraps untrusted values:

```text
<<OSII-DATA:9f3ac1>>
…source page content…
<</OSII-DATA:9f3ac1>>
```

The document cannot guess the token, so it cannot close the fence. The helper
lives in one place and every untrusted interpolation in the codebase routes
through it, so the property is auditable rather than remembered.

**2. Give the system prompt the trust rule.** The integrator's system prompt
states that fenced content is source material to be described, that
instructions found inside it are data to be reported rather than followed, and
that only the surrounding OSII prompt defines the task. Say it once, in the
system message, where it belongs.

**3. Validate output as a schema, not as a suggestion.** Parsing JSON is not
validation. Every field the model returns gets a declared type, a length cap,
and where possible a value constraint: `confidence` restricted to the three
documented values, entity and concept counts capped, names and summaries
bounded.

Evidence gets the strongest constraint available here, because the prompt
already demands a quote and OSII can check rather than trust it. The check is
lexical overlap against the full document rather than exact substring: the
prompt asks for a verbatim quote, but a small local model paraphrases and
truncates, and an exact test would reject good extractions along with invented
ones. Overlap tolerates paraphrase while rejecting evidence that shares almost
nothing with the document it claims to quote.

Entities whose evidence fails the check are dropped, which matches the existing
rule that an entity without evidence is not kept. A concept is not required to
carry evidence, so ungrounded evidence is cleared and the concept survives.
`integrator_config` accepts `evidence_grounding` with three values: `drop`, the
default; `flag`, which keeps the entity but still counts it, for an operator
measuring the effect on their own corpus before enforcing it; and `off`.

**4. Sanitize before writing into a page body.** A single function applied to
every model-supplied string that reaches markdown: images and links become
their own text, bare URLs become inline code rather than clickable targets,
wiki links lose their brackets, inline HTML and invisible characters are
removed, and line-leading `#`, `>`, and `---` markers are escaped so they
render literally. Single-line fields are flattened so they cannot begin a new
structural line at all. Structure in the wiki must come from OSII, never from a
model.

Validation and sanitization both run in `apply_integration_data`, the one place
where a response becomes files, so every later stage works with values that are
already bounded and already inert.

Escaping a marker does not remove it from the text, so any code that decides
page structure must match on anchored patterns rather than substrings.
`ensure_source_grounding_bullet` previously tested for its section with an
unanchored `in`, which a mid-line occurrence in a model summary could satisfy
while the anchored substitution below it found nothing to replace — dropping
the grounding bullet silently. Its test and its substitution now use the same
anchored pattern.

**5. Record the boundary crossing.** When the integrator drops a field or
detects fence-directed text, that is a fact about the document and belongs in
the store next to it, not in a discarded log line. Surface it in the dashboard.
A corpus where one file tried to instruct the pipeline is something the person
who owns that corpus should be able to see.

Not yet built. As an interim measure the validation report — how many entities
were received, rejected, and rejected specifically for ungrounded evidence — is
returned in the integration result and written to the wiki run log, so the
signal exists before there is a place to put it.

Still outstanding: prefix concept page filenames to resolve the reserved-name
case, matching what entity pages already do.

### What this design does not claim

It does not detect prompt injection. Detection by pattern matching fails
against paraphrase, translation, and encoding, and a detector that is trusted
is worse than no detector at all. Every layer above is either structural — the
model cannot reach the position it needs — or a constraint on output that holds
regardless of what the model was persuaded to produce. Heuristic detection is
worth adding later as *telemetry*, to tell an operator that something in their
corpus is behaving strangely. It is not worth adding as a gate.

It also does not make a poisoned corpus safe to read. If a document lies, OSII
will faithfully summarize a lie. The boundary being defended is narrower and
achievable: untrusted text must not be able to change what OSII *does*.

## Deferred surfaces

Known, unhardened, and recorded here so they are not rediscovered as
surprises. The nonce helper and the system-prompt rule from steps 1 and 2 are
shared infrastructure and apply directly to each of these once written.

- **Synthesis prompts.** Replace the literal `"""` fence in
  `object_describe_user.txt` and the recursive chunk prompt. Constrain
  `quality` and `kind` to their documented enumerations — `quality` currently
  lets a document argue for its own promotion to `high`, the tier reserved for
  guiding documents such as readmes and overviews.
- **Recursive stage boundary.** Stage-two consolidation should treat
  stage-one output as untrusted, because it is.
- **Folder overviews.** Filenames reach the model unfenced.
- **Chat, both services.** Query, scope, history, and retrieved snippets are
  flattened into one unstructured user message with no trust labelling.
  Retrieval is attacker-steerable: a document crafted to rank for a predictable
  query chooses what enters the prompt.
- **Dashboard rendering.** Restrict image and link hosts in model-derived
  markdown and add a content security policy.
- **MCP responses.** Corpus-derived text should be labelled as untrusted data
  when it crosses to an external agent, which may act on it with capabilities
  OSII does not have.

## How this gets validated

A fixture corpus under `ai-ready-ingest/tests/fixtures/injection/` holds
documents carrying representative payloads: fence escapes, forged section
headings, embedded wiki links, instruction blocks in the register of the
integrator prompt, and a distinctive canary string throughout.

Tests assert properties, not model behavior:

- integration output validates against the schema for every fixture;
- no canary string reaches a wiki page body, an entity name, or a filename;
- grounding bullets are recorded for every source that supports an entity,
  including when a fixture attempts to suppress them;
- page bodies contain no markdown images or links that OSII did not write;
- structural headings in a generated page come only from OSII's templates.

These hold whether or not a given model resists a given payload, which is the
point: the pipeline's safety should not depend on the model having a good day.
