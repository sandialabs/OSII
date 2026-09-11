ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE} AS build
ARG OSII_CA_BUNDLE_SHA256=none

WORKDIR /app
RUN echo "OSII CA bundle SHA-256: ${OSII_CA_BUNDLE_SHA256}" && \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
        mkdir -p /etc/pki/ca-trust/source/anchors && \
        cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        chmod 0644 /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        update-ca-trust; \
    fi
RUN dnf module enable nodejs:22 -y && \
    dnf install -y nodejs npm && \
    dnf clean all && \
    rm -rf /var/cache/dnf
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && rm -rf node_modules

FROM ${OSII_BASE_IMAGE}
ARG OSII_VERSION=development
ARG OSII_CA_BUNDLE_SHA256=none
LABEL org.opencontainers.image.title="OSII Dashboard" \
      org.opencontainers.image.description="Web interface for the On-Store Intelligence Index" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

RUN echo "OSII CA bundle SHA-256: ${OSII_CA_BUNDLE_SHA256}" && \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
        mkdir -p /etc/pki/ca-trust/source/anchors && \
        cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        chmod 0644 /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        update-ca-trust; \
    fi

RUN dnf install -y nginx shadow-utils && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /var/lib/osii --create-home osii

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=osii:osii /app/dist /usr/share/nginx/html

USER osii
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
