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
- Preserve source identity, stored records, and processing provenance. Keep
  credentials, library data, and generated outputs out of version control.
  Use Toolbox for frontend tools and processors for backend modules.
- When porting shared changes, retain server ownership of hosted entry points,
  session and role enforcement, collection ownership, PostgreSQL migrations,
  and `deploy/`. Use isolated PostgreSQL for integration checks and verify
  account visibility. Review migrations and deployments separately.

See the [developer guide](docs/contributing/developer-guide.md) for architecture
and validation commands.
