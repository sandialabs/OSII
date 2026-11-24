# OSII contributor guidance

- Keep changes focused and reviewable. Run the relevant checks and include the
  results and any rollout steps in the change summary. Maintainers review
  integration, release, and deployment changes.
- Develop shared Core and dashboard behavior on `main`, which also owns the
  local source workflow. `osii-server` owns hosted authentication, PostgreSQL,
  and deployment. `osii-standalone` owns Windows desktop packaging.
- Merge `main` into Standalone on an `osii-standalone-sync/<name>` integration
  branch. Keep the Windows entry points and advance `osii-standalone` after
  CI and Standalone Windows pass. Put portable fixes on `main`.
- Core owns canonical storage and RAG orchestration. The dashboard and MCP
  server use Core APIs. Reuse dashboard components across profiles and keep
  processors behind the public `osii.processor_sdk` contract.
- Give each page or view one defined scope and primary action. Use layout,
  headings, and controls to show the order. Use short, plain-language labels
  and put optional explanation behind a labeled question-mark button. Avoid
  nested drawers.
  Use the left menu or Toolbox to open tools. Keep related controls on one row
  when space permits.
- Use the shared library product names and show what each tool reads and writes
  through Core. File pages show saved products and their provenance. Give
  processing its own workspace. A tool that consumes original bytes must
  declare supported source types and check compatibility before running.
- Preserve source identity, stored records, and processing provenance. Keep
  credentials, library data, and generated outputs out of version control.
  Run intake tests with synthetic fixtures against an isolated library.
  Use Toolbox for frontend tools and processors for backend modules.
- Preserve the offline Windows installer, loopback session, bundled OCR, and
  local sidecar storage. Run the Windows installer checks for changes to
  desktop startup, bundled processing, or packaging.

See the [developer guide](docs/contributing/developer-guide.md) for architecture
and validation commands.
