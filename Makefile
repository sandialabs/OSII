# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' dev-containers
COMPOSE ?= podman-compose
UV ?= uv

.PHONY: dev dev-host dev-core dev-ollama dev-corporate dev-extractor dev-synthesizer dev-embedder dev-enricher dev-model-bridge dev-containers dev-services dev-examples containers-dev run dev-all down logs test build docs docs-serve doctor catalog-rebuild catalog-verify

# Default development path: API, worker, chat, MCP, dashboard, and extraction
# all run from source on the host. No container runtime is required.
dev: dev-host

dev-host:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

dev-core:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --core-only

dev-ollama:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --provider-profile ollama

dev-corporate:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --provider-profile corporate

dev-extractor:
	$(UV) run --python 3.11 --package osii-local-extractor uvicorn app.main:app --app-dir services/local-extractor --host 127.0.0.1 --port 8092 --reload

dev-synthesizer:
	$(UV) run --python 3.11 --package osii-local-synthesizer uvicorn app.main:app --app-dir services/local-synthesizer --host 127.0.0.1 --port 8093 --reload

dev-embedder:
	$(UV) run --python 3.11 --package osii-local-embedder uvicorn app.main:app --app-dir services/local-embedder --host 127.0.0.1 --port 8085 --reload

dev-enricher:
	$(UV) run --python 3.11 --package osii-local-enricher uvicorn app.main:app --app-dir services/local-enricher --host 127.0.0.1 --port 8094 --reload

dev-model-bridge:
	$(UV) run --python 3.11 --package osii-model-provider-bridge uvicorn app.main:app --app-dir services/model-provider-bridge --host 127.0.0.1 --port 8095 --reload

# Hybrid development for deployment-parity extraction: Tika and Tesseract use
# containers while the application services continue to run from source.
dev-containers: dev-services
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

dev-services:
	$(COMPOSE) --profile ocr up -d tika tesseract

# Start the normal integrated stack from existing images, without rebuilding.
run:
	$(COMPOSE) --profile chat --profile agents --profile ocr up local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker chat mcp dashboard tika tesseract

dev-examples: dev-services
	$(COMPOSE) --profile examples up -d --build table-pdf-enricher
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --examples

# Rebuild and run the deployment-style container stack.
containers-dev:
	$(COMPOSE) --profile chat --profile agents --profile ocr up --build local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker chat mcp dashboard tika tesseract

dev-all:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr up --build

down:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr down

logs:
	$(COMPOSE) logs -f

test:
	$(UV) sync --python 3.11 --package osii --extra dev
	$(UV) run --python 3.11 --package osii --extra dev python -m pytest ai-ready-ingest/tests
	$(UV) sync --python 3.11 --package osii-processor-sdk --extra dev
	$(UV) run --python 3.11 --package osii-processor-sdk --extra dev python -m pytest packages/osii-processor-sdk/tests
	cd ai-ready-rag-chat && $(UV) run --python 3.11 --package ai-ready-chat --extra dev python -m pytest tests
	cd services/local-extractor && $(UV) run --python 3.11 --package osii-local-extractor --extra dev python -m pytest tests
	cd services/local-synthesizer && $(UV) run --python 3.11 --package osii-local-synthesizer --extra dev python -m pytest tests
	cd services/local-embedder && $(UV) run --python 3.11 --package osii-local-embedder --extra dev python -m pytest tests
	cd services/local-enricher && $(UV) run --python 3.11 --package osii-local-enricher --extra dev python -m pytest tests
	cd services/model-provider-bridge && $(UV) run --python 3.11 --package osii-model-provider-bridge --extra dev python -m pytest tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

build:
	$(COMPOSE) --profile examples --profile chat --profile agents --profile ocr build

doctor:
	$(UV) run --no-project --python 3.11 python scripts/disk_usage.py

catalog-rebuild:
	$(UV) run --python 3.11 --package osii python -m osii.catalog_cli rebuild

catalog-verify:
	$(UV) run --python 3.11 --package osii python -m osii.catalog_cli verify

docs:
	$(UV) run --no-project --python 3.11 python scripts/check_docs_links.py
	$(UV) run --no-project --python 3.11 --with mkdocs-material mkdocs build --strict

docs-serve:
	$(UV) run --no-project --python 3.11 --with mkdocs-material mkdocs serve
