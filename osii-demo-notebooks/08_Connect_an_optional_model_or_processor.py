# %% [markdown]
# # 08 — Connect optional services without changing core OSII
#
# Model-backed chat and synthesis use any OpenAI-compatible `/v1` service.
# Domain-specific extraction or enrichment belongs in an external Processor API
# container. Neither option adds a proprietary SDK to the OSII core.

# %%
import os

from osii.model_clients import ModelCapabilityUnavailable, create_chat_client

# %%
# Uncomment and replace these only when a compatible gateway is available.
# os.environ["OSII_MODEL_BASE_URL"] = "https://models.example.internal/v1"
# os.environ["OSII_MODEL_API_KEY"] = "replace-with-a-secret"

try:
    client = create_chat_client()
except ModelCapabilityUnavailable as exc:
    print("Local-first mode is active:", exc)
else:
    answer = client.complete(
        model="your-model-name",
        messages=[{"role": "user", "content": "Reply with one sentence about grounded retrieval."}],
        max_tokens=80,
    )
    print(answer)

# %% [markdown]
# For a subject-matter processor, implement Processor API v1 and register its
# URL in the dashboard. Start with `packages/osii-processor-sdk/examples/` and
# `docs/extending/hello-enricher.md`; the processor returns typed output while
# OSII core persists the canonical `.osii` artifacts.
