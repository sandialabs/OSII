# %% [markdown]
# # 08 — Opt into Ollama, discover processors, and export a collection
#
# The basic walkthrough is already complete. This final example shows three
# modular boundaries without making any of them mandatory:
#
# 1. an Ollama model reached through OSII's HTTP-only provider bridge;
# 2. Processor API descriptor discovery;
# 3. a portable collection package containing canonical sidecars, governance,
#    and knowledge products—but not the original source files.

# %%
from __future__ import annotations

import os

from osii.domain.osii_packages import create_collection_package
from osii.domain.scopes.collections import list_collections
from osii.enrichment.llm_wiki import LlmWikiEnricher
from osii.processors.remote import RemoteSynthesizer

from _demo_support import demo_paths, heading, processor_descriptor, require_path


paths = demo_paths()
require_path(paths.osii_root / "objects", "Run scripts 00–07 first.")

OLLAMA_SYNTHESIZER_URL = "http://127.0.0.1:8095/ollama/synthesizer"
OLLAMA_MODEL = os.getenv("OLLAMA_SYNTHESIS_MODEL", "llama3.2:1b")
RUN_OLLAMA_EXAMPLE = False

descriptor = processor_descriptor(OLLAMA_SYNTHESIZER_URL)
heading("Optional Ollama synthesizer")
if descriptor is None:
    print(
        "The provider bridge is offline. Start `make dev-model-bridge` or "
        "`.\\scripts\\osii.ps1 dev-model-bridge`. Ollama itself must also be running."
    )
else:
    print(f"Discovered: {descriptor['display_name']} ({descriptor['name']})")
    print(f"Configured demonstration model: {OLLAMA_MODEL}")
    print("Set RUN_OLLAMA_EXAMPLE = True to make model calls in this script.")

collection = next(
    item for item in list_collections(paths.osii_root) if item["name"] == "Purcell analysis"
)

# %% [markdown]
# ## Optional model-backed synthesis and wiki
#
# This block is deliberately opt-in so running every `.py` example never
# surprises the user with a model call. The exact model name is explicit.

# %%
if RUN_OLLAMA_EXAMPLE:
    if descriptor is None:
        raise RuntimeError("Start Ollama and the model-provider bridge first.")

    configured = [url for url in os.environ.get("OSII_PROCESSORS", "").split(",") if url]
    if OLLAMA_SYNTHESIZER_URL not in configured:
        configured.append(OLLAMA_SYNTHESIZER_URL)
    os.environ["OSII_PROCESSORS"] = ",".join(configured)

    synthesizer = RemoteSynthesizer(descriptor)
    collection_summary = synthesizer.synthesize_scope(
        osii_store=paths.osii_root,
        scope={"scope_type": "collection", "collection_id": collection["id"]},
        expert_context="Preserve physical quantities, equations, organism names, and caveats.",
        synthesizer_config={
            "model": OLLAMA_MODEL,
            "temperature": 0.1,
            "max_tokens": 700,
        },
    )
    print("Collection synthesis:", collection_summary["result"])

    wiki = LlmWikiEnricher().enrich(
        osii_store=paths.osii_root,
        scope={"scope_type": "collection", "collection_id": collection["id"]},
        expert_context="Write for a scientist exploring Purcell's argument and examples.",
        enricher_config={
            "synthesizer_name": "ollama.synthesizer",
            "model": OLLAMA_MODEL,
            "title": "Life at Low Reynolds Number Wiki",
            "max_input_chars": 20_000,
            "max_tokens": 1_200,
        },
    )
    print("LLM wiki:", wiki["result"])

# %% [markdown]
# ## Export a portable collection sidecar

# %%
package_bytes = create_collection_package(paths.osii_root, collection["id"])
package_path = paths.exports / "purcell-analysis.osii.zip"
package_path.write_bytes(package_bytes)

heading("Portable OSII collection package")
print("Package:", package_path)
print("Bytes:", len(package_bytes))
print("Original source files included: no")

# %% [markdown]
# To build a domain-specific extractor, synthesizer, embedder, or enricher,
# copy a Processor SDK example and return typed Processor API v1 output. The
# core will validate and commit it. Start with:
#
# - `packages/osii-processor-sdk/examples/`
# - `docs/extending/hello-enricher.md`
# - `docs/reference/processor-api/index.md`
