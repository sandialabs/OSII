# Experimental OSII Model2Vec embedder

An optional Processor API v1 service, isolated from OSII's default dependencies.
See [build, deployment, and Quay commands](../README.md#model2vec-mount-an-approved-staged-model).
The container installs the `model2vec` extra, runs `local.model2vec`, and expects
an approved staged model at `/models/model2vec`. No model weights are built into
the image. Missing staged files cause startup to fail rather than download a
model or silently change the vector space.

For host development, from this folder, set these variables before running:

macOS/Linux:

```bash
export OSII_LOCAL_EMBEDDING_PROVIDER=model2vec
export OSII_OFFLINE=1
export OSII_MODEL2VEC_MODEL="/absolute/path/to/approved-model"
```

Windows PowerShell:

```powershell
$env:OSII_LOCAL_EMBEDDING_PROVIDER = "model2vec"
$env:OSII_OFFLINE = "1"
$env:OSII_MODEL2VEC_MODEL = "C:/Models/approved-model"
```

Both shells:

```sh
uv run --no-project --python 3.11 --with-editable ../../packages/osii-processor-sdk --with-editable '.[model2vec]' python -m uvicorn app.main:app --host 127.0.0.1 --port 8087
```

Open <http://127.0.0.1:8087/docs> or `/v1/descriptor` and register that base URL
as a Processor API endpoint in Setup. Model/provider changes require a new
index; never combine different vector spaces.

## Model-free contract smoke tests

The source retains its historical `local.hashing` compatibility mode for tests.
It is lexical, not semantic, and is **not** the container's default. In a fresh
terminal without the variables above, run from this folder:

```sh
uv run --no-project --python 3.11 --with-editable ../../packages/osii-processor-sdk --with-editable '.[dev]' python -m pytest tests -q
```

These tests do not validate an actual semantic model. Review Model2Vec and the
staged model independently before deployment; this example is experimental.
