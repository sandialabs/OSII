FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY services/local-extractor /workspace/services/local-extractor
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk /workspace/services/local-extractor
EXPOSE 8092
CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/services/local-extractor", "--host", "0.0.0.0", "--port", "8092"]

