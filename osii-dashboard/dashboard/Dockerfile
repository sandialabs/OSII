ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE} AS build

WORKDIR /app
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
LABEL org.opencontainers.image.title="OSII Dashboard" \
      org.opencontainers.image.description="Web interface for the On-Store Intelligence Index" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

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
