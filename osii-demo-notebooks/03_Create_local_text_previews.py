# %% [markdown]
# # 03 — Synthesize cited previews
#
# A synthesizer receives already-extracted text. It does not perform OCR or
# extraction. The guaranteed `local.extractive-preview` service selects source
# excerpts and formats cited Markdown; it does **not** generate new claims.
#
# Start the editable stack with `make dev` (macOS/Linux) or
# `.\scripts\osii.ps1 dev` (Windows). If it is offline, this script explains
# what to start and exits successfully so the rest of the walkthrough remains
# usable.

# %%
from osii.domain.read.catalog import load_files_catalog
from osii.processors.remote import RemoteSynthesizer

from _demo_support import demo_paths, heading, processor_descriptor, require_path


paths = demo_paths()
require_path(paths.osii_root / "root.toml", "Run scripts 00–02 first.")

LOCAL_SYNTHESIZER_URL = "http://127.0.0.1:8093"
descriptor = processor_descriptor(LOCAL_SYNTHESIZER_URL)

if descriptor is None:
    print(
        "Local synthesis is not running. Start `make dev-synthesizer` or "
        "`.\\scripts\\osii.ps1 dev-synthesizer`, then rerun this file."
    )
else:
    heading(f"Connected to {descriptor['display_name']}")
    print(descriptor["description"])
    synthesizer = RemoteSynthesizer(descriptor)
    documents = load_files_catalog(paths.osii_root)

    for document in documents:
        result = synthesizer.synthesize(
            osii_store=paths.osii_root,
            file_id=document["file_id"],
            expert_context="Keep measurements and experiment numbers visible.",
            synthesizer_config={"max_chars_per_document": 500},
        )
        print(f"- {document['source_relpath']} -> {result['synthesis_rel']}")

    root_result = synthesizer.synthesize_scope(
        osii_store=paths.osii_root,
        scope={"scope_type": "root"},
        synthesizer_config={"max_chars_per_document": 350},
    )
    print("\nRoot preview:", root_result["result"])

# %% [markdown]
# The service returned typed data, while core wrote the `.osii` files. That
# boundary is the same for a local baseline, Ollama bridge, or custom corporate
# synthesizer. Script 08 shows how to opt into an actual Ollama model.
