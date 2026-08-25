# %% [markdown]
# # 07 — Add models at the edge, not at the foundation
#
# The useful local workflow is already complete: grounded extraction, explicit
# scopes, lexical retrieval, optional vectors, and standard enrichments all
# exist without a generative model.
#
# This final core example shows where a model can add value without becoming a
# storage authority or a mandatory dependency. It also exports a portable
# collection sidecar for use in another workflow.

# %% [markdown]
# ## Models are processors, not hidden global state
#
# OSII reaches Ollama through an HTTP-only bridge. The model runs outside the
# core, its identity is explicit, and its result is committed as a derived
# artifact. The grounded source remains available if the model changes or goes
# offline.

# %%
from __future__ import annotations

import os

from osii.domain.osii_packages import create_collection_package
from osii.domain.scopes.collections import list_collections
from osii.enrichment.llm_wiki import LlmWikiEnricher
from osii.processors.remote import RemoteSynthesizer

from _demo_support import demo_paths, processor_descriptor, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the earlier core examples first.")

collection = next(
    item for item in list_collections(paths.osii_root)
    if item["name"] == "Purcell analysis"
)
collection_scope = {
    "scope_type": "collection",
    "collection_id": collection["id"],
}

print(collection_scope)

# %% [markdown]
# ## Discover the optional model bridge
#
# Start it only when you want this experiment:
#
# ```bash
# make dev-model-bridge
# ```
#
# Windows PowerShell:
#
# ```powershell
# .\scripts\osii.ps1 dev-model-bridge
# ```
#
# Ollama and the selected model must also be installed separately.

# %%
OLLAMA_SYNTHESIZER_URL = "http://127.0.0.1:8095/ollama/synthesizer"
OLLAMA_MODEL = os.getenv("OLLAMA_SYNTHESIS_MODEL", "llama3.2:1b")

descriptor = processor_descriptor(OLLAMA_SYNTHESIZER_URL)

if descriptor:
    print(f"Discovered: {descriptor['display_name']} ({descriptor['name']})")
    print("Model for this experiment:", OLLAMA_MODEL)
else:
    print("The model-provider bridge is offline. The rest of OSII still works.")

# %% [markdown]
# ## Make external computation an explicit choice
#
# The default is `False` so running the entire series never surprises you with
# a model call. Change the value only after inspecting the descriptor, model,
# scope, and configuration.

# %%
RUN_OLLAMA_EXAMPLE = False

print("Will call Ollama:", RUN_OLLAMA_EXAMPLE)

# %% [markdown]
# ## Register this processor for the notebook process

# %%
if RUN_OLLAMA_EXAMPLE:
    if descriptor is None:
        raise RuntimeError("Start Ollama and the model-provider bridge first.")

    processor_urls = [
        url for url in os.environ.get("OSII_PROCESSORS", "").split(",") if url
    ]
    if OLLAMA_SYNTHESIZER_URL not in processor_urls:
        processor_urls.append(OLLAMA_SYNTHESIZER_URL)
    os.environ["OSII_PROCESSORS"] = ",".join(processor_urls)

    print("Configured processors:", processor_urls)

# %% [markdown]
# ## Experiment 1: grounded collection synthesis
#
# Low temperature and bounded output make the research choice visible. The
# synthesizer receives preferred text from an explicit scope rather than
# unrestricted filesystem access.

# %%
if RUN_OLLAMA_EXAMPLE:
    synthesizer = RemoteSynthesizer(descriptor)
    collection_summary = synthesizer.synthesize_scope(
        osii_store=paths.osii_root,
        scope=collection_scope,
        expert_context=(
            "Preserve physical quantities, equations, organism names, and caveats."
        ),
        synthesizer_config={
            "model": OLLAMA_MODEL,
            "temperature": 0.1,
            "max_tokens": 700,
        },
    )
    print(collection_summary["result"])

# %% [markdown]
# ## Experiment 2: a standard wiki artifact
#
# The model produces prose, but the output uses a standard artifact family.
# That means a dashboard and an agent can consume it without Ollama-specific UI
# or storage code.

# %%
if RUN_OLLAMA_EXAMPLE:
    wiki_result = LlmWikiEnricher().enrich(
        osii_store=paths.osii_root,
        scope=collection_scope,
        expert_context=(
            "Write for a scientist exploring Purcell's argument and examples."
        ),
        enricher_config={
            "synthesizer_name": "ollama.synthesizer",
            "model": OLLAMA_MODEL,
            "title": "Life at Low Reynolds Number Wiki",
            "max_input_chars": 20_000,
            "max_tokens": 1_200,
        },
    )
    print(wiki_result["result"])

# %% [markdown]
# ## Export a portable collection sidecar
#
# Transfer is another benefit of separating canonical objects from source
# files and application databases. This package contains collection metadata,
# member sidecars, governance, and knowledge products. It intentionally excludes
# original source files, which may have different handling requirements.

# %%
package_bytes = create_collection_package(paths.osii_root, collection["id"])
package_path = paths.exports / "purcell-analysis.osii.zip"
package_path.write_bytes(package_bytes)

print("Package:", package_path)
print("Bytes:", len(package_bytes))
print("Original source files included: no")

# %% [markdown]
# ## Where to go next
#
# The core walkthrough showed reusable **consumption** patterns. The next three
# examples switch perspective and build the public extension contracts:
#
# 1. source bytes to grounded segments with a custom extractor;
# 2. scope text to cited Markdown with a custom synthesizer;
# 3. scope text to a standard entity artifact with a custom enricher.
#
# Each example uses only top-level imports from `osii_processor_sdk`, which is
# the friendly compatibility boundary for external research code.
