# OSII Toolbox guidance

These optional processors live in the main repository but remain independently
deployable. Do not add their dependencies to Core, the root uv workspace/lock,
or the baseline image. The host development launcher starts them by default
in independent environments; `OSII_START_TOOLBOX=false` opts out. Starting a
service does not authorize processing or model invocation.

- Core owns canonical `.osii` storage. Tools receive bounded requests and return
  typed results; never mount or browse the library from a processor.
- Use the shared `osii.processor_sdk` contract included in `osii`, not a copied SDK.
- Keep per-tool dependencies, tests, and API documentation.
  Run tests separately: several independent services use an `app` package name.
- Container packaging is archived. Maintain host commands and Processor API contracts.
- Never commit environments, model weights/caches, secrets, or processing data.
  Model-backed tools require explicit selection and independent security review.
- Support macOS and Windows; use `python -m uvicorn` for host commands.
