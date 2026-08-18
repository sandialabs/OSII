# %% [markdown]
# # 08 — Write a custom extractor with the public SDK
#
# An extractor defines the grounded content recovered from one source. Build one
# when a file format or domain parser knows more than a generic text tool: a
# laboratory export, simulation log, instrument stream, or specialized PDF.
#
# The extension should return typed segments and source locations. It should not
# write `.osii`, build an index, or decide how the result appears in a UI. OSII
# core handles those responsibilities after validating the response.

# %% [markdown]
# ## The friendly extension surface
#
# Everything in this notebook comes from the top-level
# `osii_processor_sdk` package. These names form the compatibility boundary for
# an independently deployed processor.

# %%
import base64

from osii_processor_sdk import (
    Capability,
    DocumentInput,
    ExtractionRequest,
    ExtractionResponse,
    Extractor,
    ProcessorDescriptor,
    ProcessorKind,
    TextSegment,
    create_processor_app,
)

# %% [markdown]
# ## Describe the processor before implementing it
#
# A descriptor lets people, OSII, and future planning agents discover identity
# and capabilities without running the research algorithm. Use a stable,
# namespaced name and a semantic version.

# %%
DELIMITED_EXTRACTOR = ProcessorDescriptor(
    name="demo.delimited-observations",
    version="1.0.0",
    display_name="Delimited Observation Extractor",
    description="Turns one pipe-delimited observation per line into grounded segments.",
    kind=ProcessorKind.EXTRACTOR,
    capabilities=Capability(
        media_types=["text/plain"],
        file_extensions=[".obs"],
        output_kinds=["text_segment"],
    ),
    config_schema={
        "type": "object",
        "properties": {
            "delimiter": {
                "type": "string",
                "title": "Field delimiter",
                "default": "|",
            }
        },
        "additionalProperties": False,
    },
)

print(DELIMITED_EXTRACTOR.model_dump())

# %% [markdown]
# ## Keep domain parsing in one small method
#
# This demonstration treats every non-empty line as a segment. `source_origin`
# preserves the line number, which is the narrowest defensible grounding for
# this format.

# %%
class DelimitedObservationExtractor(Extractor):
    descriptor = DELIMITED_EXTRACTOR

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        encoded = request.document.content_base64 or ""
        source_text = base64.b64decode(encoded).decode("utf-8")
        delimiter = request.config.get("delimiter", "|")

        segments = []
        for line_number, line in enumerate(source_text.splitlines(), start=1):
            if not line.strip():
                continue
            fields = [field.strip() for field in line.split(delimiter)]
            segments.append(
                TextSegment(
                    id=f"line-{line_number}",
                    text=" | ".join(fields),
                    segment_type="observation",
                    source_origin={"line": line_number},
                )
            )

        return ExtractionResponse(
            request_id=request.request_id,
            processor=self.descriptor,
            segments=segments,
        )

# %% [markdown]
# ## Test the algorithm without a server
#
# Processors are plain Python objects first. Direct tests are fast, deterministic,
# and easy to run in an air-gapped research environment.

# %%
sample_bytes = b"08:00 | chamber-a | 21.4 C\n08:05 | chamber-a | 21.7 C\n"

request = ExtractionRequest(
    request_id="demo-extraction-1",
    document=DocumentInput(
        filename="temperature.obs",
        media_type="text/plain",
        content_base64=base64.b64encode(sample_bytes).decode("ascii"),
    ),
    expert_context="Preserve timestamps, chamber names, values, and units.",
    config={"delimiter": "|"},
)

# %%
extractor = DelimitedObservationExtractor()
response = extractor.extract(request)

print(response.model_dump_json(indent=2))

# %% [markdown]
# Check the properties that matter to the contract: the request ID is returned,
# segment IDs are unique, and every segment points back to a source line.

# %%
assert response.request_id == request.request_id
assert len({segment.id for segment in response.segments}) == len(response.segments)
assert all("line" in segment.source_origin for segment in response.segments)

print("Contract checks passed.")

# %% [markdown]
# ## Add HTTP as a thin adapter
#
# The SDK creates `/health`, `/v1/descriptor`, and `/v1/extract`. Your algorithm
# does not need FastAPI code. In a real extension repository, put this in a
# module such as `my_extractor.py` and run `uvicorn my_extractor:app`.

# %%
app = create_processor_app(extractor)

print("Generated routes:")
for route in app.routes:
    if getattr(route, "path", "").startswith(("/health", "/v1")):
        print("-", route.path)

# %% [markdown]
# To adapt this example, replace only the parsing method and capabilities. Keep
# the typed response, narrow source grounding, and core-owned persistence. That
# separation lets a specialist extractor become a reusable tool for notebooks,
# batch workers, dashboards, and agent workflows without a core fork.
