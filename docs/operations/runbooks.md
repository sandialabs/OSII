# Running OSII

The supported path on `main` is `make dev`, or
`.\\scripts\\osii.ps1 dev` on Windows. See the
[start and troubleshooting guide](runbook-development.md).

Deployment work is archived on `archive/workstation-deployment-2026-11-03`.
The branch preserves the launcher, image catalog, Compose stack, build recipes,
publishing/export scripts, and former release pipelines. It is local until
pushed upstream. Existing installed applications and runtime data are not deleted.

The product direction is one hosted OpenShift deployment with one model endpoint
and shared database. This checkout does not yet implement that hosted deployment
or a database consolidation. See [the planning document](../planning/hosted-service.md).
