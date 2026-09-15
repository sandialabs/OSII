ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_PYTHON_VERSION=3.12
ARG OSII_CA_BUNDLE_SHA256=none
ENV PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN echo "OSII CA bundle SHA-256: ${OSII_CA_BUNDLE_SHA256}" && \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
        mkdir -p /etc/pki/ca-trust/source/anchors && \
        cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        chmod 0644 /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        update-ca-trust; \
    fi

RUN dnf install -y "python${OSII_PYTHON_VERSION}" "python${OSII_PYTHON_VERSION}-pip" shadow-utils ca-certificates && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    "python${OSII_PYTHON_VERSION}" -m venv "${VIRTUAL_ENV}" && \
    "${VIRTUAL_ENV}/bin/python" -m pip install --no-cache-dir --upgrade pip

WORKDIR /workspace
COPY osii-core/pyproject.toml osii-core/README.md /workspace/osii-core/
COPY osii-core/osii /workspace/osii-core/osii
COPY osii-core/osii_processor_sdk /workspace/osii-core/osii_processor_sdk
COPY osii-toolbox/llm-wiki-enrichers /workspace/llm-wiki-enrichers
RUN "${VIRTUAL_ENV}/bin/python" -m pip install --no-cache-dir \
    /workspace/osii-core \
    /workspace/llm-wiki-enrichers && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /workspace osii && \
    chown -R osii:osii /workspace

WORKDIR /workspace/llm-wiki-enrichers
USER osii
EXPOSE 8099 8100
ENTRYPOINT ["python", "run.py"]
CMD ["readable"]
