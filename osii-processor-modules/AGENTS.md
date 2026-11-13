# OSII processor module guidance

These optional processors live in the main repository but remain independently
deployable. Do not add their dependencies to Core, the root uv workspace/lock,
or the baseline image. The host development launcher starts them by default
in independent environments; per-module `OSII_ENABLE_…=false` switches omit
dependency setup and startup. `OSII_START_PROCESSOR_MODULES=false` defers startup. Starting a
service does not authorize processing or model invocation.

- Core owns canonical `.osii` storage. Tools receive bounded requests and return
  typed results; never mount or browse the library from a processor.
- Use the shared `osii.processor_sdk` contract included in `osii`, not a copied SDK.
- Keep each module's launch/registration metadata in `processor-module.toml`;
  never add a central Python list entry for a new module. Preserve stable processor
  IDs and declare accepted inputs/model needs in its descriptor.
- Declare offline test paths and extras in `[tool.osii.ci]` in each module's
  pyproject so the shared CI runner discovers its tests without workflow edits.
- Keep per-tool dependencies, tests, and API documentation.
  Run tests separately: several independent services use an `app` package name.
- Container packaging is archived. Maintain host commands and Processor API contracts.
- Never commit environments, model weights/caches, secrets, or processing data.
  Model-backed tools require explicit selection and independent security review.
- Support macOS and Windows; use `python -m uvicorn` for host commands.
