FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system osii && adduser --system --ingroup osii osii
WORKDIR /app

COPY ai-ready-ingest/pyproject.toml ai-ready-ingest/README.md ./
COPY ai-ready-ingest/osii ./osii
COPY ai-ready-ingest/config ./config
RUN pip install --no-cache-dir .

RUN mkdir -p /data/.osii /data/source /data/uploads && chown -R osii:osii /data

ENV SHARED_VOLUME_ROOT=/data/source \
    OSII_ROOT=/data/.osii \
    UPLOAD_ORIGINALS_ROOT=/data/uploads

USER osii
EXPOSE 8511
CMD ["python", "-m", "uvicorn", "osii.main:app", "--host", "0.0.0.0", "--port", "8511"]
