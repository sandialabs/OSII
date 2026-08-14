FROM python:3.12-slim

ARG OSII_VERSION=development
LABEL org.opencontainers.image.title="OSII Chat" \
      org.opencontainers.image.description="Grounded chat runtime for the On-Store Intelligence Index" \
      org.opencontainers.image.source="https://github.com/heidikmkv/osii" \
      org.opencontainers.image.version="${OSII_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN addgroup --system osii && adduser --system --ingroup osii osii
USER osii
EXPOSE 8611
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8611"]
