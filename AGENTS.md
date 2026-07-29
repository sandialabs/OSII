# OSII agent guidance

## Product philosophy

OSII turns a person's files into a grounded, inspectable intelligence layer.
People should be able to browse, search, and chat with their own corpus without
having to understand the storage model. Agents should use the same scopes,
provenance, retrieval results, and standard artifacts to provide detailed,
defensible answers.

OSII is local-first. Connected model services improve results but must not be
required for the basic browse, search, processing, and grounded-chat workflow.

## Platform and usability

- Development happens primarily on macOS; deployment and normal use happen
  primarily on Windows. Keep every user-facing command, path, volume mount,
  and runtime workflow cross-platform.
- Prefer Podman as the documented default. Keep Docker Compose compatible as a
  simple override.
- Keep `Makefile` shortcuts and `scripts/osii.ps1` behavior equivalent.
- Update user-facing documentation with every behavior or workflow change.
  Write for a person seeing OSII and its codebase for the first time; favor
  short, copy-pasteable paths over tool-installation tutorials.

## Modularity

- The backend, dashboard, MCP server, chat service, processor SDK, and tools
  must remain independently usable. Do not introduce an implicit dependency on
  the monorepo filesystem when a service boundary or package dependency is
  appropriate.
- Custom extractors, synthesizers, embedders, and enrichers use the documented
  processor API. The core owns canonical `.osii` persistence; processors return
  typed outputs and do not write the store directly.
- Preserve the standard table, knowledge-graph, entity-list, and wiki-Markdown
  artifact formats so dashboard and agent support stays generic.

## Validation and handoff

- Run focused tests and the relevant frontend build after changes when the
  required tools are available.
- At the end of every code-change response, give the human a concise,
  copy-pasteable Git commit command and message. Do not stage, commit, push, or
  open pull requests unless explicitly asked.

