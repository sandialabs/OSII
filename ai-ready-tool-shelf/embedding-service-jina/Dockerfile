FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/.cache/huggingface \
    TRANSFORMERS_CACHE=/models/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/.cache/sentence_transformers \
    HOST=0.0.0.0 \
    PORT=8085

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

ARG MODEL_NAME=jinaai/jina-embeddings-v2-base-en
ENV MODEL_NAME=${MODEL_NAME}
RUN mkdir -p /models && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${MODEL_NAME}', trust_remote_code=True, device='cpu')" && \
    useradd -ms /bin/bash appuser && \
    chown -R appuser:appuser /app /models

USER appuser

EXPOSE 8085

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
