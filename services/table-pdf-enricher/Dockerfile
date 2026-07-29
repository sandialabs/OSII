FROM python:3.12-slim

WORKDIR /workspace
COPY packages/osii-processor-sdk packages/osii-processor-sdk
COPY services/table-pdf-enricher services/table-pdf-enricher

RUN pip install --no-cache-dir ./packages/osii-processor-sdk ./services/table-pdf-enricher

USER 65532:65532
EXPOSE 8091
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/services/table-pdf-enricher", "--host", "0.0.0.0", "--port", "8091"]

