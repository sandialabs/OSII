# Architecture

AI Ready Chat is a thin backend-for-frontend service.

## Dependencies

It depends on:
- the OSII backend for retrieval and grounded content access
- Shirty for model invocation

## Responsibility split

### OSII backend
Owns:
- objects
- scopes
- collections
- preferred text
- canonical text spans
- enrichments
- syntheses
- grounded search

### AI Ready Chat
Owns:
- retrieval orchestration
- prompt assembly
- model invocation
- answer generation
- citation packaging

### Frontend
Owns:
- UI
- user controls
- rendering answers and citations