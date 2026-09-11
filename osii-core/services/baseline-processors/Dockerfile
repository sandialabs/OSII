ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_VERSION=development
ARG OSII_PYTHON_VERSION=3.12
ARG OSII_CA_BUNDLE_SHA256=none
LABEL org.opencontainers.image.title="OSII Baseline Processors" \
      org.opencontainers.image.description="Selectable local processors and model-provider bridge for OSII" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN echo "OSII CA bundle SHA-256: ${OSII_CA_BUNDLE_SHA256}" && \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
        mkdir -p /etc/pki/ca-trust/source/anchors && \
        cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        chmod 0644 /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        update-ca-trust; \
    fi

RUN dnf install -y python3 python3-pip shadow-utils ca-certificates && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    python3 -m pip install --no-cache-dir uv && \
    uv python install "${OSII_PYTHON_VERSION}" && \
    uv venv "${VIRTUAL_ENV}" --python "${OSII_PYTHON_VERSION}"

WORKDIR /workspace
COPY osii-core/processor-sdk /workspace/processor-sdk
RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" \
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

RUN groupadd --system osii && useradd --system --gid osii --home-dir /workspace osii && \
    chown -R osii:osii /workspace
USER osii

EXPOSE 8085 8092 8093 8094 8095
ENTRYPOINT ["python", "/workspace/run.py"]
CMD ["extractor"]
