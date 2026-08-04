# Model provider bridge

HTTP-only adapters for Ollama and generic OpenAI-compatible services. The
bridge never downloads a model and stores no credentials. Configure models
explicitly, run it on port 8095, and use these Processor API base URLs:

- `/ollama/embedder`
- `/ollama/synthesizer`
- `/openai/embedder`
- `/openai/synthesizer`

Chat-compatible routes are exposed at `/{provider}/v1/chat/completions`.
