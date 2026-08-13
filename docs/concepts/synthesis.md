# Synthesis architecture

Synthesis reads extracted OSII text and produces a derived, human-readable
interpretation for an object, folder, collection, or the complete library. It
is broader than summarization: a synthesizer may create a cited preview, source
guide, description, comparison, or report.

Extraction and synthesis are deliberately separate. Extraction establishes
canonical text and grounding; synthesis can then be repeated with a different
prompt or provider without reopening or changing the source file.

## The normal service boundary

New synthesizers implement [Processor API v1](../reference/processor-api/synthesis.md).
They receive an explicit scope containing document text and return:

- Markdown;
- provenance citations;
- processor identity and method metadata;
- optional warnings.

The processor does not read or write `.osii`. OSII core validates the response
and commits the synthesis variant so the result remains portable and
inspectable.

The guaranteed `local.extractive-preview` service is a model-free example. It
selects short source excerpts and formats cited Markdown. It is not OCR, does
not interpret the corpus, and does not generate new claims.

Ollama, generic OpenAI-compatible services, and Shirty are model providers.
Thin bridges adapt them to the same synthesis contract, so Intake and the
dashboard do not need provider-specific persistence logic.

## Scopes and outputs

| Scope | Input | Canonical synthesis variants |
|---|---|---|
| Object | One preferred text representation | `objects/<file-id>/syntheses/` |
| Folder | Text from structural folder membership | `folders/folder-<id>.syntheses/` |
| Collection | Text from logical collection membership | `collections/<id>/syntheses/` |
| Root | Text from the complete library | `syntheses/` |

Compatibility files such as `synth.txt` may also exist for older readers, but
named synthesis variants preserve multiple methods without forcing one model's
result to overwrite another.

## Prompt and model identity

A model-backed synthesis should record enough information to explain and
reproduce its behavior:

- synthesizer descriptor name and version;
- provider and exact model name;
- prompt/instructions and user-adjustable settings;
- input extraction identity when available;
- whether expert context was used;
- citations and creation time.

Changing a prompt creates a new derived result; it does not change extracted
text. Tools exposes descriptor-defined settings such as instructions,
temperature, and output limits. Custom processors publish a JSON Schema in
their descriptor so an SME can expose settings without writing frontend code.

## Expert context

Optional expert context supplies facts or conventions that are not reliably
inferable from source text, for example:

- experiment naming conventions;
- expected units or control groups;
- domain terminology;
- the intended comparison or emphasis.

Processors should distinguish expert context from source evidence. Provenance
records whether it was supplied, and factual claims should still cite source
documents whenever the corpus supports them.

## Fallback behavior

Synthesis and chat may fall back by capability: a corporate provider can fall
back to selected Ollama and finally to an explicitly labeled extractive
baseline. The UI must always identify the method actually used. An extractive
preview must never be presented as an LLM-generated synthesis.

Legacy in-process synthesizers remain only for compatibility while service
parity is proven. They are not advertised in normal Intake or demo choices.
New work belongs behind Processor API v1.

## Build a synthesizer

1. Start with the [Processor SDK overview](../reference/processor-api/index.md).
2. Implement the typed `Synthesizer` interface and publish a descriptor.
3. Return cited Markdown without writing `.osii`.
4. Contract-test `/health`, `/v1/descriptor`, `/v1/synthesize`, and OpenAPI.
5. Register the service in Tools, test it, and select it for an Intake action.

For an executable client and commit-adapter example, run
`osii-demo-notebooks/03_Create_local_text_previews.py`. For a model-backed
knowledge product, see the [LLM wiki walkthrough](../tutorials/llm-wiki.md).
