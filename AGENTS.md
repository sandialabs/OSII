# OSII contributor guidance

- Keep changes focused and reviewable. Run the relevant checks and include the
  results and any rollout steps in the change summary. Maintainers review
  integration, release, and deployment changes.
- Develop shared Core and dashboard behavior on `main`, which also owns the
  local source workflow. `osii-server` owns hosted authentication, PostgreSQL,
  and deployment. `osii-standalone` owns Windows desktop packaging.
- Bring shared changes into delivery branches on a separate integration branch.
  Review focused commits and their prerequisites against the target branch.
  Keep platform-specific entry points and validate the target profile.
- Core owns canonical storage and RAG orchestration. The dashboard and MCP
  server use Core APIs. Reuse dashboard components across profiles and keep
  processors behind the public `osii.processor_sdk` contract.
- Give each page or view one defined scope and primary action. Use layout,
  headings, and controls to show the order. Keep copy short and put optional
  explanation behind a labeled question-mark button. Avoid nested drawers.
- Use the shared library product names and show what each tool reads and writes
  through Core. File pages show saved products and their provenance. Give
  processing its own workspace. A tool that consumes original bytes must
  declare supported source types and check compatibility before running.
- Preserve source identity, stored records, and processing provenance. Keep
  credentials, library data, and generated outputs out of version control.
  Use Toolbox for frontend tools and processors for backend modules.
- Keep the source launcher working on macOS and Windows. OSII-local runs on
  loopback without user accounts and uses sidecars by default. PostgreSQL is
  opt-in, and the inventory SQLite database has its own lifecycle.

See the [developer guide](docs/contributing/developer-guide.md) for architecture
and validation commands.
