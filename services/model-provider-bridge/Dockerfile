FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY services/model-provider-bridge /workspace/service
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk /workspace/service
EXPOSE 8095
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/service", "--host", "0.0.0.0", "--port", "8095"]
