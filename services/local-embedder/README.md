# Local embedder

Processor API v1 service `local.hashing`. Run `make dev-embedder` and open
<http://localhost:8085/docs>. It returns deterministic, normalized 384D token
and bigram hashing vectors with model identity `osii-local-hashing-v1`.

Semantic embedding is supplied by an optional model-provider bridge. Changing
providers or models requires rebuilding the selected semantic index.
