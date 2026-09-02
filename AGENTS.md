# OSII agent guidance

## Product philosophy

OSII turns a person's files into a grounded, inspectable intelligence layer.
People should be able to browse, search, and chat with their own corpus without
having to understand the storage model. Agents should use the same scopes,
provenance, retrieval results, and standard artifacts to provide detailed,
defensible answers.

OSII is local-first. Connected model services improve results but must not be
required for the basic browse, search, processing, and grounded-chat workflow.

OSII is both a research project and a working implementation. Code,
documentation, and demonstrations should help a new contributor understand the
ideas being tested, not merely reproduce the current behavior. Preserve the
research questions, architectural boundaries, and tradeoffs in forms a person
can inspect and discuss.

## Human-first design

- Optimize first for a technically curious person reading the code. Prefer
  explicit data flow, descriptive names, small units, and ordinary Python over
  clever abstractions, hidden registration, or framework magic.
- Make the important architectural decision visible near the code that depends
  on it. Comments and prose should explain why a boundary or invariant exists,
  not narrate syntax that is already apparent.
- Introduce concepts before machinery. User-facing guides and demonstrations
  should explain the object model and purpose of an operation before presenting
  commands, configuration, or a long code block.
- Keep examples small enough to copy and adapt. Break multi-stage examples into
  named steps with inspectable intermediate results instead of presenting one
  opaque end-to-end function.
- Do not make a user understand the monorepo layout to use OSII. Provide a
  coherent public Python or service boundary and keep deployment plumbing out of
  the normal learning path.
- Prefer one obvious documented workflow over several equivalent environment or
  launch choices. When separate environments or services are intentional,
  explain who owns each one and why it exists.

## Code structure and public surfaces

- Organize modules around stable domain concepts and capabilities. Avoid vague
  grab-bag modules, large coordinator objects, and layers that exist only to
  forward calls without clarifying ownership.
- Keep dependencies pointing inward: domain logic and typed contracts must not
  depend on FastAPI routes, dashboard components, container layouts, or process
  launchers. Adapters may depend on the domain, not the reverse.
- Keep side effects at the edges. Pass paths, scopes, processor choices, and
  configuration explicitly; avoid import-time environment resolution and
  hidden mutation of global state in reusable logic.
- Prefer typed request/response models, dataclasses, and named result objects at
  public boundaries over undocumented dictionaries. When compatibility
  requires a dictionary, document its stable keys and validate it at the edge.
- Give each function or class one conceptual responsibility and a name that
  describes it in OSII vocabulary. Extract helpers when they reveal a meaningful
  step, not merely to reduce line count.
- Add an abstraction only when it makes ownership, substitution, or testing
  clearer. Do not generalize a one-off research path before a real second use
  demonstrates the shared contract.
- A new public operation needs a stable import path, focused tests, and one
  small usage example. Treat breaking public imports or Processor API contracts
  as deliberate migrations rather than incidental refactors.

## Architectural principles

- Grounding comes before generation. Preserve source identity, extracted text,
  source locations, and provenance so every later product can be inspected and
  defended.
- Canonical data comes before acceleration. SQLite catalogs, BM25/FAISS indexes,
  caches, and model outputs are derived and rebuildable; ordinary portable
  `.osii` sidecars remain authoritative.
- Processors compute; OSII core persists. A processor receives an explicit,
  bounded request and returns typed data. The core validates lineage, chooses
  canonical paths, and commits the result.
- Context must be explicit. Objects and root, folder, collection, and object
  scopes are shared vocabulary for Python, REST, the dashboard, MCP, and future
  agents. Do not substitute ambient filesystem access for a declared scope.
- Models are optional methods, not authorities. Record provider, model,
  configuration, and limitations with derived results, and retain a useful
  local/model-free baseline wherever practical.
- Build for people now and agents later. An agent should use the same scoped,
  provenance-bearing resources a person can inspect rather than a parallel
  opaque representation.

## Interpretability and research honesty

- Label experimental, heuristic, model-backed, emulated, and production-ready
  behavior accurately. Do not imply semantic understanding, extraction quality,
  or provider equivalence that has not been measured.
- Keep algorithms independently testable from HTTP, containers, queues, and UI
  adapters. A researcher should be able to exercise representative domain logic
  with a small typed Python request.
- Store enough method identity and configuration to compare or reproduce
  results. Replacing a processor or vector space must not silently overwrite the
  evidence or make incompatible outputs appear equivalent.
- Favor inspectable intermediate artifacts and narrow provenance over a single
  unexplained score or generated answer.

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

- The OSII Core package owns RAG orchestration and the grounded chat API. The
  dashboard and MCP server remain independent clients of Core; the processor
  SDK and tools remain independently usable. Do not introduce an implicit
  dependency on the monorepo filesystem when a service boundary or package
  dependency is appropriate.
- Custom extractors, synthesizers, embedders, and enrichers use the documented
  processor API. The core owns canonical `.osii` persistence; processors return
  typed outputs and do not write the store directly.
- Preserve the standard table, knowledge-graph, entity-list, and wiki-Markdown
  artifact formats so dashboard and agent support stays generic.
- Treat `osii_processor_sdk` as the public compatibility boundary for external
  processors. Extension examples should use its top-level imports rather than
  teaching core storage internals.
- Grow a deliberate, friendly public surface for the `osii` Python package.
  Avoid making normal users compose deep internal modules when a stable,
  cohesive operation can express the same workflow.
- Keep domain logic separate from transport and persistence adapters. Prefer a
  small pure or typed operation that can be tested directly, then wrap it with
  HTTP, queue, CLI, or UI integration.
- New capabilities should identify whether they are extraction, synthesis,
  embedding, enrichment, retrieval, or canonical store behavior. Do not blur
  those responsibilities merely to shorten an implementation.
- Avoid UI-only features that bypass the domain model. A meaningful capability
  should be available through an appropriate Python/service API so scripts,
  the dashboard, and agents can share it.

## Component placement and development discipline

Classify a capability before creating its first file. Do not use a convenient
directory as a temporary home for a runnable service; its location is part of
the architecture and deployment contract.

| Destination | Owns | Must not contain |
| --- | --- | --- |
| OSII Core and baseline processor packages | Canonical storage, RAG and chat orchestration, dashboard/API/MCP clients, and the smallest guaranteed local processing path | Model weights, specialized OCR, domain-specific processors, or optional deployment services |
| OSII Model Tool Chest | Independently deployable, swappable OCR, model, and domain-specific Processor API containers that a deployment may select by default | Core persistence, dashboard logic, or an implicit Core dependency |
| `examples/` and documentation | Short snippets, fixtures, request/response samples, and non-runnable teaching material | FastAPI/Flask apps, Dockerfiles, processor packages, service launch wiring, or a second application stack |
| AI-ready tool shelf | Explicitly experimental or one-off utilities that are not a recommended OSII deployment component | A hidden Core default or a substitute for a maintained Tool Chest service |

- A runnable HTTP processor, container image, or separately versioned package
  belongs in the Model Tool Chest when it is optional or replaceable. It needs
  a component directory with a package manifest, Dockerfile, focused tests,
  README, and an OSII Processor API contract available inside the image.
- A processor runs from an explicit bounded request and returns typed output;
  Core validates and persists it. It must not browse the user's corpus, write
  canonical `.osii` files, or reach into dashboard/Core internals.
- Do not add optional Tool Chest services to Core's default Compose set,
  baseline image, `make dev`, PowerShell launcher, or `.env` defaults. A human
  or deployment chooses them through `OSII_PROCESSORS` or deployment-owned
  wiring.
- Retain tutorial data importers and fixtures in Core only when they do not
  implement or start a processor. Documentation must state both the component
  owner and how a person explicitly configures it.
- Before changing a boundary, update the owning component's README and the
  relevant Core deployment/tutorial documentation in the same change. Do not
  add a second launch path merely to make a demonstration convenient.

## Documentation and demonstrations

- Teach the OSII philosophy as part of the workflow: untouched originals,
  portable sidecars, explicit scopes, replaceable computation, standard
  artifacts, and provenance-bearing results.
- Start with a guaranteed local or model-free path. Introduce OCR services,
  model providers, corporate bridges, and other optional components only at the
  step where they add value.
- Put setup, environment ownership, prerequisites, and the expected visible
  result next to the first step that needs them. Never assume a new user knows
  which virtual environment, service, port, or working directory is intended.
- Prefer public, copyable examples for extractors, synthesizers, embedders, and
  enrichers. Show descriptor, typed request, direct test, typed response, and
  thin service adapter as separate concepts.
- Give readers deliberate inspection pauses: show where canonical files,
  provenance, scope definitions, standard artifacts, and rebuildable indexes
  were written and what each means.
- Keep prose cross-platform and cross-repository. Use relative repository paths
  where the target ships together; use plain path examples rather than binding
  reusable documentation to one hosting URL.

## Planned cleanup

- `ai-ready-ingest` is a transitional directory name. Plan a dedicated,
  reviewable rename to `osii-code`, including workspace metadata, container
  paths, tests, documentation, and component-export mappings. Do not mix that
  repository-wide rename into unrelated feature work.

## Validation and handoff

- Run focused tests and the relevant frontend build after changes when the
  required tools are available.
- At the end of every code-change response, give the human a concise,
  copy-pasteable Git commit command and message. Do not stage, commit, push, or
  open pull requests unless explicitly asked.
- At the end of every code-change response, also give the human a concise,
  copy-pasteable command to apply or launch the change and view its result.
  Include required rebuild/restart steps when container code or configuration
  changed; do not imply that an already-running container updates itself.

## Notebook safety

- Treat `.ipynb` files as opaque artifacts. Do not read, edit, format, or
  rewrite them unless the human explicitly asks to work on a named notebook.
- Use the paired `.py` source files for review and normal code changes. When a
  named legacy notebook needs a Python counterpart, run
  `scripts/notebook_to_py.py` rather than opening its JSON. For the canonical
  demonstration set, use `osii-demo-notebooks/manage_notebooks.py` to convert
  all examples safely in either direction.
