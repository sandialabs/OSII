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
- OSII-local has no user authentication, accounts, roles, or login screen.
  Hosted user authentication belongs exclusively to the server profile. Keep local
  processes on loopback; processor/provider credentials and private internal
  service tokens are separate from user authentication.
- File metadata inventory is part of normal OSII-local, not a separate branch
  or startup mode. `osii.volume` owns its separate canonical SQLite inventory
  on local disk. Never rebuild, quarantine, or replace it as a sidecar catalog.
  Metadata scanning must not read file contents, hash files, or invoke models.
- The Core owns canonical persistence, RAG orchestration, and grounded chat.
  Processors receive explicit bounded requests and return typed output; they do
  not browse a corpus or write the canonical store.
- Reuse the common browse, file, search, model-field, and topic components across
  local and server; adapt API data at each product boundary instead of forking widgets.
- Keep domain logic independent of transport, UI, launchers, and deployment.
  Keep side effects at the edges and make paths, scopes, processors, and
  configuration explicit.
- The dashboard and MCP server are Core clients. Guaranteed baseline Processor
  API hosts live under `osii-core/services/`. `osii-processor-modules/` owns separately
  deployable processor modules. Reserve "Toolbox" for frontend tools. The host
  development stack starts processor modules by default, with explicit per-module
  opt-outs, using their independent environments.
  Starting a tool does not select it for processing or invoke a model.
- Treat `osii.processor_sdk` as the public boundary for external processors.
  Preserve standard artifact formats so people, the dashboard, and agents can
  inspect the same results.

## Interface guidance

- Keep screens concise. Put explanations behind accessible, labeled question-mark
  buttons that open focused help dialogs. Prefer these to persistent paragraphs
  or additional drawers. Keep essential state, errors, and actions visible.

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

## Branches and merges

- Use `main` for current OSII Dev, Windows Standalone, and hosted Server work.
  Start new feature branches from `origin/main` in their own worktrees when
  working in parallel. Keep the existing branch folders in place for Codex.
- To sync a feature branch, run `git fetch origin` from its worktree. Confirm the
  checked-out branch and that the worktree is clean with `git status --short --branch`,
  then run `git merge origin/main`. Resolve conflicts in that feature branch.
  Review the merge against the current behavior of each affected delivery profile
  and run its relevant checks before pushing to `origin`.
- Treat `osii-standalone` and `osii-server` as maintenance branches for the
  earlier Windows and hosted releases. Land shared fixes on `main`, then backport
  only the needed commits and prerequisites with `git cherry-pick -x <commit>`
  when an older release needs them. Adapt and test each backport against the
  receiving branch. Merge the full `origin/main` history into a maintenance
  branch only for an explicitly requested baseline upgrade.
- Keep desktop packaging and loopback behavior with the desktop profile.
  Keep hosted authorization, PostgreSQL, and deployment behavior with the
  server profile. A merge does not authorize a database migration or deployment.

## Current delivery scope

- Windows Standalone builds on `main` from Electron, the frozen Python
  runtime, bundled Tesseract, and the default dashboard. Preserve the offline
  per-user installer, private loopback session, library lock, and existing
  library data. Keep user startup free of runtime package installs, container
  engines, registries, Java, and model weights. Validate the installed app on
  Windows. Use the unsigned pilot label until signing and clean standard-user
  acceptance are complete.
- Hosted Server builds on `main` from its own API, worker, and hosted dashboard.
  Keep account administration and authorization in that profile. Local uses
  sidecars by default and permits explicitly initialized PostgreSQL in source
  development. Server requires its hosted PostgreSQL schema. Keep storage
  contracts stable and local inventory evidence separate from rebuildable indexes.

- The supported startup path on main is `make dev` (Windows:
  `.\\scripts\\osii.ps1 dev`). Keep automatic dependency setup, logs, health
  checks, and Ctrl+C shutdown working. Do not add alternative startup menus.
- Product direction is one shared OpenShift deployment, independent model capability
  endpoints, and one shared database. Hosted migrations and administrator
  bootstrap remain explicit operations.
- Historical container-based workstation deployment is archived on `archive/workstation-deployment-2026-11-03`.
  Restore that deployment only when explicitly requested.
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
  `manage_notebooks.py` on the `osii-demo-notebooks` branch for intentional conversions.
- Automatically stage and commit completed, validated task changes locally.
  Use focused commits, preserve unrelated work, and do not ask the user to
  copy-paste commit commands. This is standing authorization for local commits.
- Automatically push completed, tested task changes after committing them to
  the current branch on `origin` (the user's GitHub repository). This is standing
  authorization to push; do not ask for confirmation or leave the push to the user.
  Preserve unrelated work, use normal non-force pushes, and resolve any remote
  divergence without discarding changes. Do not push to `upstream` or open a pull
  request unless the user explicitly asks.
- Report local commit hashes and relevant validation results. Include run or
  inspection instructions when needed, including required rebuild or restart
  steps.

## Naming

Frontend tools live in the dashboard **Toolbox**. Backend modules are **processors**
and live under `osii-processor-modules/`. Preserve existing Processor API IDs and
artifact provenance when changing display names.
