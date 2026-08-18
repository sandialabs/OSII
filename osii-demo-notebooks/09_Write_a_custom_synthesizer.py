# %% [markdown]
# # 09 — Write a grounded synthesizer
#
# A synthesizer explains text that OSII has already extracted. It can create a
# preview, technical summary, comparison, or narrative over one object or a
# larger scope. It must preserve citations because a readable answer is only as
# valuable as the evidence a person or agent can revisit.

# %% [markdown]
# ## Import the public contract

# %%
from osii_processor_sdk import (
    Capability,
    DocumentInput,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    ScopeInput,
    SynthesisRequest,
    SynthesisResponse,
    Synthesizer,
    create_processor_app,
)

# %% [markdown]
# ## Declare which scopes the method supports
#
# The method below can operate over any supplied documents, so it advertises
# object, folder, collection, and root scopes. A narrower domain method should
# advertise only what it can defend.

# %%
FIRST_SENTENCE_SYNTHESIZER = ProcessorDescriptor(
    name="demo.first-sentence",
    version="1.0.0",
    display_name="First Sentence Synthesizer",
    description="Builds deterministic cited Markdown from the first sentence of each object.",
    kind=ProcessorKind.SYNTHESIZER,
    capabilities=Capability(
        scope_types=["object", "folder", "collection", "root"],
        output_kinds=["markdown"],
    ),
)

print(FIRST_SENTENCE_SYNTHESIZER.model_dump())

# %% [markdown]
# ## Implement narrative and grounding together
#
# This model-free method is intentionally simple. A model-backed implementation
# can replace sentence selection, but it should still return citations in the
# same response type.

# %%
class FirstSentenceSynthesizer(Synthesizer):
    descriptor = FIRST_SENTENCE_SYNTHESIZER

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        sections = []
        citations = []

        for document in request.scope.documents:
            text = (document.text or "").strip()
            sentence = text.split(".", maxsplit=1)[0].strip()
            if sentence:
                sentence += "."
                sections.append(f"## {document.filename}\n\n{sentence}")
                citations.append(
                    ProvenanceRef(
                        file_id=document.file_id,
                        char_start=0,
                        char_end=len(sentence),
                    )
                )

        return SynthesisResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            markdown="\n\n".join(sections),
            citations=citations,
        )

# %% [markdown]
# ## Build an explicit scope snapshot
#
# A processor receives only the documents selected for this request. It does not
# crawl the store or infer authority from a mounted directory.

# %%
scope = ScopeInput(
    scope_type="collection",
    scope_id="demo-collection",
    documents=[
        DocumentInput(
            file_id="object-alpha",
            filename="alpha.txt",
            text="Viscosity dominates motion at low Reynolds number. Inertia is negligible.",
        ),
        DocumentInput(
            file_id="object-beta",
            filename="beta.txt",
            text="Reciprocal motion cannot produce net swimming. The stroke must break symmetry.",
        ),
    ],
)

request = SynthesisRequest(
    request_id="demo-synthesis-1",
    scope=scope,
    expert_context="Keep the physical claim and its source object visible.",
)

# %% [markdown]
# ## Test the research method directly

# %%
synthesizer = FirstSentenceSynthesizer()
response = synthesizer.synthesize(request)

print(response.markdown)
print("Citations:", [citation.model_dump() for citation in response.citations])

# %%
assert response.request_id == request.request_id
assert len(response.citations) == len(scope.documents)
assert {citation.file_id for citation in response.citations} == {
    document.file_id for document in scope.documents
}

print("Grounding checks passed.")

# %% [markdown]
# ## Wrap the same object as a service

# %%
app = create_processor_app(synthesizer)

print("Generated routes:")
for route in app.routes:
    if getattr(route, "path", "").startswith(("/health", "/v1")):
        print("-", route.path)

# %% [markdown]
# A richer implementation can call a local model, a remote approved endpoint,
# or deterministic scientific code. The stable part is the contract: explicit
# scope in, grounded Markdown and citations out, canonical persistence left to
# OSII core.
