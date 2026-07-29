FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /workspace

COPY ai-ready-ingest /workspace/ai-ready-ingest
COPY ai-ready-mcp /workspace/ai-ready-mcp
RUN pip install --no-cache-dir /workspace/ai-ready-ingest /workspace/ai-ready-mcp

RUN addgroup --system osii && adduser --system --ingroup osii osii
USER osii
EXPOSE 8021
CMD ["osii-mcp"]

