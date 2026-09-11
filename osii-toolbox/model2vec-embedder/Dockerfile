ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_PYTHON_VERSION=3.12
ARG OSII_CA_BUNDLE_SHA256=none
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
COPY osii-core/processor-sdk /workspace/osii-core/processor-sdk
COPY osii-toolbox/model2vec-embedder /workspace/model2vec-embedder
RUN uv pip install --no-sources --python "${VIRTUAL_ENV}/bin/python" \
    /workspace/osii-core/processor-sdk \
    '/workspace/model2vec-embedder[model2vec]' && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /workspace osii && \
    mkdir -p /models && \
    chown -R osii:osii /workspace /models

ENV OSII_LOCAL_EMBEDDING_PROVIDER=model2vec \
    OSII_OFFLINE=1 \
    OSII_MODEL2VEC_MODEL=/models/model2vec
USER osii
EXPOSE 8085
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/workspace/model2vec-embedder", "--host", "0.0.0.0", "--port", "8085"]
