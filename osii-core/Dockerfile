ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE}

ARG OSII_VERSION=development
ARG OSII_PYTHON_VERSION=3.12
LABEL org.opencontainers.image.title="OSII Core" \
      org.opencontainers.image.description="API, worker, and grounded chat runtime for the On-Store Intelligence Index" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# The base image supplies only the bootstrap Python. uv installs the application
# interpreter so changing to an approved RHEL-family base does not change OSII's
# Python version.
RUN dnf install -y python3 python3-pip shadow-utils ca-certificates && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    python3 -m pip install --no-cache-dir uv && \
    uv python install "${OSII_PYTHON_VERSION}" && \
    uv venv "${VIRTUAL_ENV}" --python "${OSII_PYTHON_VERSION}"

RUN groupadd --system osii && useradd --system --gid osii --home-dir /app osii
WORKDIR /app

COPY osii-core/processor-sdk ./processor-sdk
RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" ./processor-sdk
COPY osii-core/pyproject.toml osii-core/README.md ./
COPY osii-core/osii ./osii
COPY osii-core/config ./config
RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" .

RUN mkdir -p /data/.osii /data/source /data/uploads && \
    chown -R osii:osii /app /data

ENV SHARED_VOLUME_ROOT=/data/source \
    OSII_ROOT=/data/.osii \
    UPLOAD_ORIGINALS_ROOT=/data/uploads

USER osii
EXPOSE 8511
CMD ["python", "-m", "uvicorn", "osii.main:app", "--host", "0.0.0.0", "--port", "8511"]
