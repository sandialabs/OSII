# Archived deployment workflow

This workflow is retired on `main`. Use [the host startup guide](runbook-development.md)
and `make dev` (Windows: `.\\scripts\\osii.ps1 dev`).

The complete previous implementation and this runbook are preserved on branch
`archive/workstation-deployment-2026-11-03`, commit
`0cc430e45cb0e47ee0fd6fc0681bf40c8167bce0`.

Inspect an archived file without switching branches:

```bash
git show archive/workstation-deployment-2026-11-03:docs/operations/component-export.md
```

The archive branch is local until a maintainer pushes it upstream. Future
OpenShift delivery will be designed around the shared service; workstation
installers and registry catalogs are deferred.
