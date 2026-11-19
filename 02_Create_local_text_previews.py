# %% [markdown]
# # 02 — Separate "what the source says" from "how we explain it"
#
# Extraction recovered grounded text. Synthesis now creates a useful reading
# view over that text. Keeping those stages separate preserves the evidence
# while allowing many explanations—short, detailed, model-free, model-backed,
# domain-specific—to coexist.
#
# This example uses `local.extractive-preview`. It selects excerpts and adds
# citations; it does not generate new claims and requires no model.

# %% [markdown]
# ## Why synthesis is a processor
#
# A synthesizer receives an explicit object or scope snapshot and returns
# grounded Markdown. It does not re-open the original PDF and it does not write
# the store. Those limits make it independently testable and safe to replace.
#
# Start the normal stack from the repository root:
#
# ```bash
# make dev
# ```

# %%
from osii.domain.read.catalog import load_files_catalog
from osii.processors.remote import RemoteSynthesizer

from _demo_support import demo_paths, processor_descriptor, require_path

# %%
paths = demo_paths()
require_path(paths.osii_root / "objects", "Run the extraction example first.")

documents = load_files_catalog(paths.osii_root)
print(f"Objects available for synthesis: {len(documents)}")

# %% [markdown]
# ## Discover the available implementation

# %%
LOCAL_SYNTHESIZER_URL = "http://127.0.0.1:8093"
descriptor = processor_descriptor(LOCAL_SYNTHESIZER_URL)

if descriptor is None:
    print("Local synthesis is offline. Start the service, then rerun this cell.")
else:
    print(descriptor["display_name"])
    print(descriptor["description"])
    print("Supported scopes:", descriptor["capabilities"].get("scope_types", []))

# %% [markdown]
# Discovery is more than a health check. A UI or agent can inspect capabilities
# before planning work instead of guessing whether a processor accepts an
# object, collection, folder, or complete root scope.

# %% [markdown]
# ## Configure intent separately from mechanics
#
# `expert_context` describes what a good result should preserve. Processor
# configuration controls bounded mechanics such as excerpt length. Keeping the
# two distinct makes experiments easier to compare.

# %%
EXPERT_CONTEXT = (
    "Keep physical quantities, named entities, source references, and "
    "important caveats visible."
)
SYNTHESIZER_CONFIG = {"max_chars_per_document": 500}

print("Research guidance:", EXPERT_CONTEXT)
print("Mechanical settings:", SYNTHESIZER_CONFIG)

# %% [markdown]
# ## Create a preview for one object
#
# Starting with one object makes the contract easy to inspect before applying
# it to a complete corpus.

# %%
synthesizer = RemoteSynthesizer(descriptor) if descriptor else None
first_document = documents[0] if documents else None

if synthesizer and first_document:
    first_result = synthesizer.synthesize(
        osii_store=paths.osii_root,
        file_id=first_document["file_id"],
        expert_context=EXPERT_CONTEXT,
        synthesizer_config=SYNTHESIZER_CONFIG,
    )
    print(first_document["source_relpath"])
    print("Committed synthesis:", first_result["synthesis_rel"])
else:
    print("Preview paused until a document and synthesizer are available.")

# %% [markdown]
# ## Reuse the operation for remaining objects
#
# Because every object has the same stable identity and preferred-text
# semantics, the loop contains no file-format logic. Extraction already handled
# that concern.

# %%
if synthesizer:
    for document in documents[1:]:
        result = synthesizer.synthesize(
            osii_store=paths.osii_root,
            file_id=document["file_id"],
            expert_context=EXPERT_CONTEXT,
            synthesizer_config=SYNTHESIZER_CONFIG,
        )
        print(f"- {document['source_relpath']} -> {result['synthesis_rel']}")

# %% [markdown]
# ## Change scale by changing scope
#
# An OSII scope is an explicit set of objects. The same conceptual operation
# can target one object, a physical folder, a curated collection, or the whole
# root. This is a key building block for agents: scope is data that can be
# inspected, authorized, logged, and handed to another processor.

# %%
if synthesizer:
    root_result = synthesizer.synthesize_scope(
        osii_store=paths.osii_root,
        scope={"scope_type": "root"},
        synthesizer_config={"max_chars_per_document": 350},
    )
    print("Root-scope result:", root_result["result"])

# %% [markdown]
# The service returned typed data; OSII core chose canonical paths and committed
# the synthesis. A local baseline, Ollama model, or corporate implementation can
# replace the compute step without changing how objects and scopes are stored.
