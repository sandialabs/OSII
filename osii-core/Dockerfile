ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi@sha256:8f989cc9270da6abec0144c22846ed1e6e92e462dc7768ce0981c4ac1d574733
FROM ${OSII_BASE_IMAGE}
USER 0
RUN --mount=type=secret,id=osii_ca_bundle \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
      cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-corporate.pem && update-ca-trust; fi
RUN dnf install -y python3.12 python3.12-pip libgomp && dnf clean all && rm -rf /var/cache/dnf
WORKDIR /app
COPY osii-core/requirements-server.txt /app/requirements.txt
RUN python3.12 -m pip install --no-cache-dir --require-hashes -r requirements.txt
COPY osii-core/ /app/osii-core/
RUN python3.12 -m pip install --no-cache-dir --no-build-isolation --no-deps /app/osii-core && \
    mkdir -p /data/source && chgrp -R 0 /app /data && chmod -R g=u /app /data
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OSII_SOURCE_DIR=/data/source
USER 1001
EXPOSE 8512
CMD ["python3.12", "-m", "uvicorn", "osii.server.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8512"]
