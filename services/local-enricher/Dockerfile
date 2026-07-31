FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY services/local-enricher /workspace/services/local-enricher
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk /workspace/services/local-enricher
EXPOSE 8094
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/services/local-enricher", "--host", "0.0.0.0", "--port", "8094"]

