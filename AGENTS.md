# OSII agent guidance

## Human command and scope

The agent's job is to execute the human's command—nothing more.

- The repository structure is intentional: work within its existing modules,
  packages, and documentation locations.
- Do not invent folders, example directories, files, services, launch paths,
  abstractions, or supporting work. Create a file or directory only when the
  human explicitly requests it or it is strictly required by the requested
  change.
- Keep changes small, direct, and inspectable. Do not broaden the task,
  reorganize adjacent code, or perform cleanup beyond the requested scope.
- Before changing a boundary or adding a dependency, explain why it is required
  and obtain direction if it materially expands the request.

## Architecture

- OSII is local-first. Preserve original source identity, extracted text,
  locations, scopes, provenance, and portable `.osii` sidecars. Catalogs,
  indexes, caches, and model output are derived and rebuildable.
- The Core owns canonical persistence, RAG orchestration, and grounded chat.
  Processors receive explicit bounded requests and return typed output; they do
  not browse a corpus or write the canonical store.
- Keep domain logic independent of transport, UI, launchers, and deployment.
  Keep side effects at the edges and make paths, scopes, processors, and
  configuration explicit.
- The dashboard and MCP server are Core clients. Guaranteed baseline Processor
  API hosts live under `osii-core/services/`. `osii-toolbox/` owns separately
  deployable tools. Toolbox processors are enabled only through explicit
  configuration and do not join the default host stack automatically.
- Treat `osii.processor_sdk` as the public boundary for external processors.
  Preserve standard artifact formats so people, the dashboard, and agents can
  inspect the same results.

## Implementation and documentation

- Prefer ordinary, typed Python; descriptive names; small focused units; and
  stable public interfaces. Add an abstraction only when it clarifies a real
  second use.
- Label experimental, heuristic, model-backed, and production behavior
  accurately. Never make model output or ambient filesystem access authoritative.
- Keep normal commands and documentation cross-platform: macOS development and
  Windows use are both supported. Keep `Makefile` and `scripts/osii.ps1`
  workflows equivalent.
- Keep README.md a concise, durable introduction to OSII: its purpose, major
  capabilities, and how to get started.
- Update it when a change affects that information. Don’t add branch-specific
  implementation details, task summaries, temporary status, or a running list
  of changes.
- Put detailed technical explanations in docs/, decisions in an architecture
  decision record, and change history in the changelog or pull request
  description, as appropriate.
- Before finishing, review the README diff for relevance, duplication, and
  clarity to a new reader.
- Update relevant documentation only when the requested behavior or workflow
  changes. Keep examples and demonstrations small and inspectable; do not
  create new example material unless explicitly requested.

## Current delivery scope

- `main` is the standalone, filesystem-backed application. `osii-server` is
  developed separately for PostgreSQL, hosted accounts, and OpenShift. Keep
  portable fixes isolated for transfer between the branches; never merge server
  persistence or hosted startup into main implicitly.

- The supported startup path on main is `make dev` (Windows:
  `.\\scripts\\osii.ps1 dev`). Keep automatic dependency setup, logs, health
  checks, and Ctrl+C shutdown working. Do not add alternative startup menus.
- Product direction is one shared OpenShift deployment, one configured model
  endpoint, and one shared database. This does not authorize an implicit
  database migration or claim that hosted authentication is implemented.
- Desktop installers, workstation catalogs, Compose, component splitting, and
  image publishing are archived on `archive/workstation-deployment-2026-11-03`.
  Do not reintroduce them without an explicit human request.
- Preserve Core, dashboard, SDK, and processor boundaries while simplifying
  delivery. Optional tools stay optional. Do not replace existing persistence
  or delete user data as part of deployment cleanup.
- Keep CI focused on product tests, dashboard builds, and documentation. Future
  OpenShift delivery should target the shared service, not workstation installs.
- If containers are introduced for the hosted service, use the shared approved
  RHEL/UBI base, minimal non-root runtimes, pinned verified dependencies, and
  corporate certificate/mirror support. Stop on unavailable approved dependencies.

## Validation and handoff

- Run focused tests and the relevant frontend build when available and
  proportionate to the change.
- Do not read, edit, format, or rewrite `.ipynb` files unless the human names
  the notebook. Use paired `.py` sources; use
  `osii-demo-notebooks/manage_notebooks.py` for intentional conversions.
- Automatically stage and commit completed, validated task changes locally.
  Use focused commits, preserve unrelated work, and do not ask the user to
  copy-paste commit commands. This is standing authorization for local commits.
- Do not push or open a pull request unless the user explicitly asks. The user
  currently handles upstream pushes.
- Report local commit hashes and relevant validation results. Include run or
  inspection instructions when needed, including required rebuild or restart
  steps.
