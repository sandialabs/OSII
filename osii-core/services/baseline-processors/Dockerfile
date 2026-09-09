FROM python:3.12-slim

ARG OSII_VERSION=development
LABEL org.opencontainers.image.title="OSII Baseline Processors" \
      org.opencontainers.image.description="Selectable local processors and model-provider bridge for OSII" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY osii-core/processor-sdk /workspace/processor-sdk
RUN pip install --no-cache-dir \
    /workspace/processor-sdk \
    "uvicorn[standard]>=0.35,<1" \
    "PyMuPDF>=1.24" \
    "docx2txt>=0.8" \
    "requests>=2.32,<3"

COPY osii-core/services/local-extractor /workspace/services/local-extractor
COPY osii-core/services/local-synthesizer /workspace/services/local-synthesizer
COPY osii-core/services/local-embedder /workspace/services/local-embedder
COPY osii-core/services/local-enricher /workspace/services/local-enricher
COPY osii-core/services/model-provider-bridge /workspace/services/model-provider-bridge
COPY osii-core/services/baseline-processors/run.py /workspace/run.py
COPY osii-core/services/baseline-processors/PROCESSOR_API.md /workspace/PROCESSOR_API.md

RUN addgroup --system osii && adduser --system --ingroup osii osii
USER osii

EXPOSE 8085 8092 8093 8094 8095
ENTRYPOINT ["python", "/workspace/run.py"]
CMD ["extractor"]
