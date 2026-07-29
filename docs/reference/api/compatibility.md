# API compatibility notes

## Purpose

This document summarizes compatibility surfaces and removed route families during the transition to the current resource-oriented API.

## Preferred route families

New consumers should prefer the current resource-oriented route families:

- `/api/scopes/...`
- `/api/collections/...`
- `/api/objects/...`
- `/api/text/...`
- `/api/enrichments/...`
- `/api/search`

These routes reflect the current backend API direction.

## Compatibility read routes

Compatibility read routes under `/api/osii/...` are still implemented.

They remain useful for:

- older consumers
- migration support
- direct inspection of legacy read surfaces

However, they should be treated as compatibility routes, not the preferred primary API for new integrations.

## Removed route families

The following route families have been removed and should not appear in current API integrations:

- `/api/dashboard/...`
- dashboard/workbench HTML routes

The backend no longer treats dashboard rendering as part of the repository's core API surface.

## Migration guidance

When updating existing integrations:

- replace dashboard-oriented routes with resource-oriented routes
- prefer `/api/objects/...` over legacy object inspection surfaces
- prefer `/api/text/...` for grounded span access
- prefer `/api/scopes/...` for root, folder, collection, and object scope handling
- prefer `/api/enrichments/...` for derived enrichment retrieval

## Documentation policy

The main API documentation should emphasize current resource-oriented routes.

Compatibility routes may be mentioned briefly for migration purposes, but they should not dominate the main route documentation.
