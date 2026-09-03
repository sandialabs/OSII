FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/.cache/sentence_transformers \
    HOST=0.0.0.0 \
    PORT=8085

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

ARG MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
ENV MODEL_NAME=${MODEL_NAME}
RUN mkdir -p /models && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${MODEL_NAME}', device='cpu', tokenizer_kwargs={'clean_up_tokenization_spaces': True})" && \
    useradd -ms /bin/bash appuser && \
    chown -R appuser:appuser /app /models

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER appuser

EXPOSE 8085

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
