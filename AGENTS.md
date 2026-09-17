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
  deployable tools: only an explicitly designated bundled, default-swappable
  service may appear in the default packaged Compose stack; every other Toolbox
  processor is enabled only through explicit deployment configuration.
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

## Container policy

- Every OSII-authored builder and runtime stage must derive from the approved
  RHEL/UBI image supplied through the shared `OSII_BASE_IMAGE`. Do not introduce
  Fedora, Debian, Ubuntu, Alpine, or a service-specific base-image argument.
- A missing RPM is not justification for changing distributions. Build missing
  software from pinned, checksum-verified source artifacts on RHEL/UBI. If the
  approved repositories and artifact sources cannot satisfy the build, stop
  and report the dependency instead of silently choosing another base.
- Corporate source downloads must work through the configured artifact mirror
  and `OSII_CA_BUNDLE`. Install corporate trust before any package, source,
  Python, Node, or model download.
- Keep final runtime stages minimal and non-root. Published builds must use an
  approved immutable RHEL/UBI base reference; the public development default
  may use the designated UBI 9 tag.
- Preserve the simple `make build` and `make run` interface. Keep Make and
  PowerShell container workflows equivalent when container policy changes.

## Public and corporate delivery

- Treat public GitHub as the portable development and validation repository.
  Routine GitHub pushes run focused Linux/Python 3.12 and frontend checks;
  reserve cross-platform installation checks for tags or manual runs, and do
  not publish corporate images, installers, endpoints, or credentials there.
- Treat corporate GitLab as the release authority. Import public changes on a
  branch, preserve the corporate configuration layer, and merge through a
  reviewed GitLab merge request before creating a protected `vX.Y.Z` tag.
- Corporate tags build from approved mirrors and an immutable RHEL/UBI base,
  publish or reuse verified AMD64/ARM64 images in corporate Quay, and attach
  signed launcher installers to the GitLab Release. Publish a new internal
  `osii` Python package only when Core/SDK changes.
- Keep stack releases immutable. A component-only release may reuse a prior
  package version and image digests; every new stack release still gets a
  launcher pinned to its version. Never reuse a published tag.
- Corporate Quay `:latest` is a separately approved alias of a tested
  immutable release, never a build target or launcher default.
- Preserve a simple non-developer path: install the signed launcher, choose a
  source folder, pull tested images, and open the dashboard. Validate that path
  on a clean workstation before announcing a release.
- Keep `.github/workflows/ci.yml`, `.gitlab-ci.yml`, `release.toml`, and the
  operations runbooks consistent when release behavior changes.

## Validation and handoff

- Run focused tests and the relevant frontend build when available and
  proportionate to the change.
- Do not read, edit, format, or rewrite `.ipynb` files unless the human names
  the notebook. Use paired `.py` sources; use
  `osii-demo-notebooks/manage_notebooks.py` for intentional conversions.
- Do not stage, commit, push, or open a pull request unless explicitly asked.
- For a code change, end with concise commands to commit and to run or inspect
  the result, including required rebuild or restart steps.
