# Fedora is the public RPM-family default because its repositories include
# Tesseract. Set OSII_TESSERACT_BASE_IMAGE to an approved RHEL-family image in
# environments whose configured repositories provide these same RPM packages.
ARG OSII_TESSERACT_BASE_IMAGE=registry.fedoraproject.org/fedora:latest
FROM ${OSII_TESSERACT_BASE_IMAGE}

ARG OSII_PYTHON_VERSION=3.12
ARG OSII_CA_BUNDLE_SHA256=none
ENV PYTHONUNBUFFERED=1 \
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

RUN dnf install -y \
        python3 \
        python3-pip \
        shadow-utils \
        ca-certificates \
        tesseract \
        tesseract-langpack-eng \
        tesseract-langpack-fra \
        tesseract-langpack-deu \
        tesseract-langpack-spa \
        tesseract-langpack-jpn \
        tesseract-langpack-kor \
        tesseract-langpack-chi_sim \
        tesseract-langpack-ara \
        glib2 \
        libSM \
        libXext \
        libXrender \
        libgomp && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    python3 -m pip install --no-cache-dir uv && \
    uv python install "${OSII_PYTHON_VERSION}" && \
    uv venv "${VIRTUAL_ENV}" --python "${OSII_PYTHON_VERSION}"

WORKDIR /workspace
COPY osii-core/processor-sdk /workspace/osii-core/processor-sdk
COPY osii-toolbox/osii-tesseract/requirements.txt /workspace/osii-tesseract/requirements.txt
WORKDIR /workspace/osii-tesseract
RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" \
    -r requirements.txt \
    /workspace/osii-core/processor-sdk

COPY osii-toolbox/osii-tesseract/app ./app
COPY osii-toolbox/osii-tesseract/README.md ./README.md
COPY osii-toolbox/osii-tesseract/config ./config
COPY osii-toolbox/osii-tesseract/docs ./docs
RUN groupadd --system osii && \
    useradd --system --gid osii --home-dir /workspace/osii-tesseract osii && \
    chown -R osii:osii /workspace

USER osii
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
