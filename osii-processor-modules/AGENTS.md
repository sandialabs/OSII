# OSII processor module guidance

These optional processors live in the main repository but remain independently
deployable. Do not add their dependencies to Core, the root uv workspace/lock,
the baseline image, or the host development launcher implicitly.

- Core owns canonical persistence. Processors receive bounded requests and return
  typed results; never mount or browse the library from a processor.
- Use the shared `osii.processor_sdk` contract included in `osii`, not a copied SDK.
- Keep launch/registration metadata in `processor-module.toml` and offline test
  declarations in `[tool.osii.ci]` in the module pyproject. No central lists
  should be edited when adding a processor.
- Keep per-processor dependencies, tests, and API documentation.
  Run tests separately: several independent services use an `app` package name.
- Container packaging is archived. Maintain host commands and Processor API contracts.
- Never commit environments, model weights/caches, secrets, or processing data.
  Model-backed processors require explicit selection and independent security review.
- Support macOS and Windows; use `python -m uvicorn` for host commands.
