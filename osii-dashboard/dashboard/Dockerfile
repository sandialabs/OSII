ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi@sha256:8f989cc9270da6abec0144c22846ed1e6e92e462dc7768ce0981c4ac1d574733
FROM ${OSII_BASE_IMAGE} AS build
USER 0
RUN --mount=type=secret,id=osii_ca_bundle \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
      cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-corporate.pem && update-ca-trust; fi
RUN dnf module enable nodejs:22 -y && dnf install -y nodejs npm && dnf clean all
WORKDIR /app
COPY osii-dashboard/dashboard/package*.json ./
RUN npm ci
COPY osii-dashboard/dashboard/ ./
RUN npm run build
FROM ${OSII_BASE_IMAGE}
USER 0
RUN --mount=type=secret,id=osii_ca_bundle \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
      cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-corporate.pem && update-ca-trust; fi
RUN dnf install -y nginx && dnf clean all && rm -rf /var/cache/dnf
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/openshift/nginx.conf /etc/nginx/nginx.conf
USER 1001
EXPOSE 8080
CMD ["nginx", "-e", "stderr", "-g", "daemon off;"]
