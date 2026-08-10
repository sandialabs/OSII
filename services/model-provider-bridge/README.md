# Model provider bridge

HTTP-only adapters for Ollama and generic OpenAI-compatible services. The
bridge never bundles a model and stores no credentials. OSII Tools may send an
explicit, allowlisted pull request directly to a separately running Ollama
service. Configure models explicitly, run it on port 8095, and use these
Processor API base URLs:

- `/ollama/embedder`
- `/ollama/synthesizer`
- `/openai/embedder`
- `/openai/synthesizer`

Chat-compatible routes are exposed at `/{provider}/v1/chat/completions`.
