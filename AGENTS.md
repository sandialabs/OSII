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

- `main` is OSII-local: standalone and filesystem-backed. This branch,
  `osii-server`, is the hosted PostgreSQL application. Preserve source identity,
  text, locations, scopes, and provenance in PostgreSQL. Never fall back to a
  `.osii` directory or SQLite here. Retrieval caches are derived and rebuildable.
- Only Core API/worker access PostgreSQL; the UI and processors never do.
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
- Update relevant documentation only when the requested behavior or workflow
  changes. Keep examples and demonstrations small and inspectable; do not
  create new example material unless explicitly requested.

## Current delivery scope

- The supported startup path on main is `make dev` (Windows:
  `.\\scripts\\osii.ps1 dev`). Keep automatic dependency setup, logs, health
  checks, and Ctrl+C shutdown working. Do not add alternative startup menus.
- This branch implements one shared OpenShift deployment, one configured model
  endpoint, and PostgreSQL. Migrations and administrator bootstrap are explicit
  CLI operations. Keep password authentication and server permission checks on
  every corpus/admin API; never expose a development authentication bypass.
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
- Do not stage, commit, push, or open a pull request unless explicitly asked.
- For a code change, end with concise commands to commit and to run or inspect
  the result, including required rebuild or restart steps.
