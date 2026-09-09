ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_PYTHON_VERSION=3.12
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN dnf install -y python3 python3-pip shadow-utils ca-certificates && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    python3 -m pip install --no-cache-dir uv && \
    uv python install "${OSII_PYTHON_VERSION}" && \
    uv venv "${VIRTUAL_ENV}" --python "${OSII_PYTHON_VERSION}"

WORKDIR /workspace
COPY osii-core /workspace/osii-core
COPY osii-mcp /workspace/osii-mcp
RUN uv pip install --no-sources --python "${VIRTUAL_ENV}/bin/python" \
    /workspace/osii-core/processor-sdk \
    /workspace/osii-core \
    /workspace/osii-mcp && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /workspace osii && \
    chown -R osii:osii /workspace

USER osii
EXPOSE 8022
CMD ["osii-mcp"]
