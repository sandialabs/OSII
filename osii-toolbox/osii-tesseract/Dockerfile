ARG OSII_BASE_IMAGE=registry.access.redhat.com/ubi9/ubi:latest
FROM ${OSII_BASE_IMAGE} AS trust-base

ARG OSII_CA_BUNDLE_SHA256=none
RUN echo "OSII CA bundle SHA-256: ${OSII_CA_BUNDLE_SHA256}" && \
    if [ -f /run/secrets/osii_ca_bundle ]; then \
        mkdir -p /etc/pki/ca-trust/source/anchors && \
        cp /run/secrets/osii_ca_bundle /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        chmod 0644 /etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem && \
        update-ca-trust; \
    fi

FROM trust-base AS native-builder

ARG OSII_TESSERACT_SOURCE_URL=https://codeload.github.com/tesseract-ocr/tesseract/tar.gz/refs/tags/5.5.3
ARG OSII_LEPTONICA_SOURCE_URL=https://github.com/DanBloomberg/leptonica/releases/download/1.87.0/leptonica-1.87.0.tar.gz
ARG OSII_TESSDATA_BASE_URL=https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0

RUN dnf install -y \
        ca-certificates \
        cmake \
        gcc \
        gcc-c++ \
        gzip \
        libjpeg-turbo-devel \
        libpng-devel \
        libtiff-devel \
        make \
        pkgconf-pkg-config \
        tar \
        zlib-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Source versions and checksums are repository-controlled. Corporate builds may
# replace only the URLs with byte-identical copies from an approved mirror.
RUN mkdir -p /build/downloads /build/leptonica /build/tesseract /opt/tesseract/share/tessdata && \
    curl --fail --location --retry 3 --output /build/downloads/leptonica.tar.gz "${OSII_LEPTONICA_SOURCE_URL}" && \
    echo "c73363397f96eb1295602bf44d708a994ad42046c791bf03ea0505d829bdb6a7  /build/downloads/leptonica.tar.gz" | sha256sum --check --strict && \
    tar --extract --gzip --file /build/downloads/leptonica.tar.gz --directory /build/leptonica --strip-components=1 && \
    cmake -S /build/leptonica -B /build/leptonica-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/tesseract \
        -DCMAKE_INSTALL_LIBDIR=lib64 \
        -DBUILD_PROG=OFF \
        -DENABLE_ZLIB=ON \
        -DENABLE_PNG=ON \
        -DENABLE_JPEG=ON \
        -DENABLE_TIFF=ON \
        -DENABLE_GIF=OFF \
        -DENABLE_WEBP=OFF \
        -DENABLE_OPENJPEG=OFF && \
    cmake --build /build/leptonica-build --parallel 2 && \
    cmake --install /build/leptonica-build && \
    curl --fail --location --retry 3 --output /build/downloads/tesseract.tar.gz "${OSII_TESSERACT_SOURCE_URL}" && \
    echo "9218e62793116d42a9f6d14cd9348518b27f382096eea3d0f2d1a24616bb5884  /build/downloads/tesseract.tar.gz" | sha256sum --check --strict && \
    tar --extract --gzip --file /build/downloads/tesseract.tar.gz --directory /build/tesseract --strip-components=1 && \
    PKG_CONFIG_PATH=/opt/tesseract/lib64/pkgconfig cmake -S /build/tesseract -B /build/tesseract-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/tesseract \
        -DCMAKE_INSTALL_LIBDIR=lib64 \
        -DBUILD_TRAINING_TOOLS=OFF \
        -DBUILD_TESTS=OFF \
        -DGRAPHICS_DISABLED=ON \
        -DOPENMP_BUILD=OFF \
        -DDISABLE_ARCHIVE=ON \
        -DDISABLE_CURL=ON && \
    cmake --build /build/tesseract-build --parallel 2 && \
    cmake --install /build/tesseract-build

RUN set -eu; \
    for artifact in \
        "eng:7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2" \
        "fra:ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca" \
        "deu:19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d" \
        "spa:6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464" \
        "jpn:1f5de9236d2e85f5fdf4b3c500f2d4926f8d9449f28f5394472d9e8d83b91b4d" \
        "kor:6b85e11d9bbf07863b97b3523b1b112844c43e713df8b66418a081fd1060b3b2" \
        "chi_sim:a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730" \
        "ara:e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729"; do \
        language="${artifact%%:*}"; \
        checksum="${artifact#*:}"; \
        target="/opt/tesseract/share/tessdata/${language}.traineddata"; \
        curl --fail --location --retry 3 --output "${target}" "${OSII_TESSDATA_BASE_URL}/${language}.traineddata"; \
        echo "${checksum}  ${target}" | sha256sum --check --strict; \
    done; \
    rm -rf /opt/tesseract/include /opt/tesseract/lib64

FROM trust-base AS runtime

ARG OSII_BASE_IMAGE
ARG OSII_VERSION=development
ARG OSII_PYTHON_VERSION=3.12
LABEL org.opencontainers.image.title="OSII Tesseract" \
      org.opencontainers.image.description="OpenCV region detection and Tesseract OCR Processor API service" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}" \
      org.opencontainers.image.base.name="${OSII_BASE_IMAGE}" \
      org.osii.tesseract.version="5.5.3" \
      org.osii.leptonica.version="1.87.0" \
      org.osii.tessdata.version="fast-4.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    TESSDATA_PREFIX=/opt/tesseract/share/tessdata \
    PATH=/opt/venv/bin:/opt/tesseract/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN dnf install -y \
        ca-certificates \
        glib2 \
        libjpeg-turbo \
        libpng \
        libSM \
        libstdc++ \
        libtiff \
        libXext \
        libXrender \
        python3 \
        python3-pip \
        shadow-utils \
        zlib && \
    dnf clean all && \
    rm -rf /var/cache/dnf && \
    python3 -m pip install --no-cache-dir uv && \
    uv python install "${OSII_PYTHON_VERSION}" && \
    uv venv "${VIRTUAL_ENV}" --python "${OSII_PYTHON_VERSION}"

COPY --from=native-builder /opt/tesseract /opt/tesseract

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
RUN tesseract --version && \
    test "$(tesseract --list-langs 2>/dev/null | tail -n +2 | wc -l)" -eq 8 && \
    groupadd --system osii && \
    useradd --system --gid osii --home-dir /workspace/osii-tesseract osii && \
    chown -R osii:osii /workspace

USER osii
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
