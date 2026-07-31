FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY services/local-embedder /workspace/services/local-embedder
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk /workspace/services/local-embedder
EXPOSE 8085
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/services/local-embedder", "--host", "0.0.0.0", "--port", "8085"]

