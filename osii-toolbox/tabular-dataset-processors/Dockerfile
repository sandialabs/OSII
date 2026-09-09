FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace
COPY osii-core/processor-sdk /workspace/osii-core/processor-sdk
COPY osii-toolbox/tabular-dataset-processors /workspace/tabular-dataset-processors

RUN pip install --no-cache-dir \
    /workspace/osii-core/processor-sdk \
    /workspace/tabular-dataset-processors

WORKDIR /workspace/tabular-dataset-processors
EXPOSE 8097 8098
ENTRYPOINT ["python", "run.py"]
CMD ["extractor"]
