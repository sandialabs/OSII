# OSII Toolbox guidance

These optional processors live in the main repository but remain independently
deployable. Do not add their dependencies to Core, the root uv workspace/lock,
the baseline image, or the host development launcher implicitly.

- Core owns canonical `.osii` storage. Tools receive bounded requests and return
  typed results; never mount or browse the library from a processor.
- Use the shared `packages/osii-processor-sdk` contract, not a copied SDK.
  MiniLM is an OpenAI-compatible provider, connected through the model bridge.
- Keep per-tool dependencies, container definitions, tests, and API documentation.
  Run tests separately: several independent services use an `app` package name.
- Build SDK-dependent images from the repository root. MiniLM has a standalone
  build context. Keep commands accurate in `README.md` when paths change.
- Never commit environments, model weights/caches, secrets, or processing data.
  Model-backed tools require explicit selection and independent security review.
- Support macOS and Windows; use `python -m uvicorn` for host commands.
