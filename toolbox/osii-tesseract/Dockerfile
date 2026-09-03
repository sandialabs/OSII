FROM python:3.12-slim

ENV DEBIAN_FRONTEND="noninteractive" \
    PYTHONUNBUFFERED="1" \
    PIP_NO_CACHE_DIR="1"

RUN set -ex && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-transport-https \
        ca-certificates \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-fra \
        tesseract-ocr-deu \
        tesseract-ocr-spa \
        tesseract-ocr-jpn \
        tesseract-ocr-kor \
        tesseract-ocr-chi-sim \
        tesseract-ocr-ara \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY toolbox/osii-tesseract/requirements.txt /workspace/osii-tesseract/requirements.txt
WORKDIR /workspace/osii-tesseract
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk

COPY toolbox/osii-tesseract/app ./app
COPY toolbox/osii-tesseract/README.md ./README.md
COPY toolbox/osii-tesseract/config ./config
COPY toolbox/osii-tesseract/docs ./docs

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
