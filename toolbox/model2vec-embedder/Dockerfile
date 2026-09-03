FROM python:3.12-slim
WORKDIR /workspace
COPY packages/osii-processor-sdk /workspace/packages/osii-processor-sdk
COPY toolbox/model2vec-embedder /workspace/model2vec-embedder
RUN pip install --no-cache-dir /workspace/packages/osii-processor-sdk '/workspace/model2vec-embedder[model2vec]'
ENV OSII_LOCAL_EMBEDDING_PROVIDER=model2vec OSII_OFFLINE=1 OSII_MODEL2VEC_MODEL=/models/model2vec
EXPOSE 8085
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/workspace/model2vec-embedder", "--host", "0.0.0.0", "--port", "8085"]
