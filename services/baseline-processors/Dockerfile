FROM python:3.12-slim

ARG OSII_VERSION=development
LABEL org.opencontainers.image.title="OSII Baseline Processors" \
      org.opencontainers.image.description="Selectable local processors and model-provider bridge for OSII" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
RUN pip install --no-cache-dir \
    /workspace/packages/osii-processor-sdk \
    "uvicorn[standard]>=0.35,<1" \
    "PyMuPDF>=1.24" \
    "docx2txt>=0.8" \
    "requests>=2.32,<3"

COPY services/local-extractor /workspace/services/local-extractor
COPY services/local-synthesizer /workspace/services/local-synthesizer
COPY services/local-embedder /workspace/services/local-embedder
COPY services/local-enricher /workspace/services/local-enricher
COPY services/model-provider-bridge /workspace/services/model-provider-bridge
COPY services/baseline-processors/run.py /workspace/run.py

RUN addgroup --system osii && adduser --system --ingroup osii osii
USER osii

EXPOSE 8085 8092 8093 8094 8095
ENTRYPOINT ["python", "/workspace/run.py"]
CMD ["extractor"]
