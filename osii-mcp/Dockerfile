FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /workspace

COPY osii-core /workspace/osii-core
COPY osii-mcp /workspace/osii-mcp
RUN pip install --no-cache-dir /workspace/osii-core /workspace/osii-mcp

RUN addgroup --system osii && adduser --system --ingroup osii osii
USER osii
EXPOSE 8021
CMD ["osii-mcp"]

