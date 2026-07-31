# Local embedder

Processor API v1 service `local.hashing`. Run `make dev-embedder` and open
<http://localhost:8085/docs>. It returns deterministic, normalized 384D token
and bigram hashing vectors with model identity `osii-local-hashing-v1`.

For an explicitly staged semantic upgrade, install the `model2vec` extra, set
`OSII_LOCAL_EMBEDDING_PROVIDER=model2vec` and `OSII_MODEL2VEC_MODEL`, and restart.
Changing modes requires rebuilding existing indexes.
