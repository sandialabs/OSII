ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_PYTHON_VERSION=3.12
ARG OSII_CA_BUNDLE_SHA256=none
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/models/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/.cache/sentence_transformers \
    HOST=0.0.0.0 \
    PORT=8085 \
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

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" -r requirements.txt
COPY app ./app

ARG MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
ENV MODEL_NAME=${MODEL_NAME}
RUN mkdir -p /models && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${MODEL_NAME}', device='cpu', tokenizer_kwargs={'clean_up_tokenization_spaces': True})" && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /app osii && \
    chown -R osii:osii /app /models

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
USER osii

EXPOSE 8085
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
