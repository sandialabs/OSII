# Local statistics and keywords enricher

Processor API v1 service `local.stats-keywords`. Run `make dev` and
open <http://localhost:8094/docs>. `POST /v1/enrich` returns the standard OSII
table artifact format, so core can commit it and the dashboard can render it
without processor-specific frontend code.
