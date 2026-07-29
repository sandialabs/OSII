# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' dev
COMPOSE ?= podman-compose

.PHONY: dev run dev-examples dev-all down logs test build docs docs-serve

dev:
	$(COMPOSE) --profile chat --profile ocr up --build embeddings api worker chat dashboard tika tesseract

# Start the normal integrated stack from existing images, without rebuilding.
run:
	$(COMPOSE) --profile chat --profile ocr up embeddings api worker chat dashboard tika tesseract

dev-examples:
	$(COMPOSE) --profile examples --profile ocr up --build embeddings api worker chat dashboard tika tesseract table-pdf-enricher

dev-all:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr --profile embeddings --profile ollama up --build

down:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr --profile embeddings --profile ollama down

logs:
	$(COMPOSE) logs -f

test:
	uv sync --package osii --extra dev
	uv run --package osii --extra dev pytest ai-ready-ingest/tests
	uv sync --package osii-processor-sdk --extra dev
	uv run --package osii-processor-sdk --extra dev pytest packages/osii-processor-sdk/tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

build:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr --profile embeddings build

docs:
	python scripts/check_docs_links.py
	mkdocs build --strict

docs-serve:
	mkdocs serve
