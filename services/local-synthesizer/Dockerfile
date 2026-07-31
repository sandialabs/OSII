FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY services/local-synthesizer /workspace/services/local-synthesizer
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk /workspace/services/local-synthesizer
EXPOSE 8093
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/services/local-synthesizer", "--host", "0.0.0.0", "--port", "8093"]

