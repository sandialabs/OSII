# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' dev-containers
COMPOSE ?= podman-compose
UV ?= uv
OSII_IMAGE_PREFIX ?= localhost/osii
OSII_IMAGE_TAG ?= latest
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
export OSII_IMAGE_PREFIX OSII_IMAGE_TAG
export OSII_COMPOSE_COMMAND := $(COMPOSE)
unexport VIRTUAL_ENV

.PHONY: dev dev-host dev-core dev-ollama dev-commercial dev-corporate dev-extractor dev-synthesizer dev-embedder dev-enricher dev-model-bridge dev-ocr-host dev-tika dev-containers dev-containers-insecure dev-services dev-examples containers-dev run dev-all down logs test build build-release push-release docs docs-serve doctor catalog-rebuild catalog-verify provider-check

# Default development path: API (including chat), worker, MCP, dashboard, and extraction
# all run from source on the host. Setup can start optional Tika when a container
# runtime is available; the core development stack does not require one.
dev: dev-host

dev-host:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

dev-core:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --core-only

dev-ollama:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --provider-profile ollama

dev-commercial:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --provider-profile commercial

dev-corporate:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --provider-profile corporate

provider-check:
	$(UV) run --no-project --python 3.11 python scripts/check_openai_endpoint.py

dev-extractor:
	$(UV) run --python 3.11 --package osii-local-extractor python -m uvicorn app.main:app --app-dir services/local-extractor --host 127.0.0.1 --port 8092 --reload

dev-synthesizer:
	$(UV) run --python 3.11 --package osii-local-synthesizer python -m uvicorn app.main:app --app-dir services/local-synthesizer --host 127.0.0.1 --port 8093 --reload

dev-embedder:
	$(UV) run --python 3.11 --package osii-local-embedder python -m uvicorn app.main:app --app-dir services/local-embedder --host 127.0.0.1 --port 8085 --reload

dev-enricher:
	$(UV) run --python 3.11 --package osii-local-enricher python -m uvicorn app.main:app --app-dir services/local-enricher --host 127.0.0.1 --port 8094 --reload

dev-model-bridge:
	$(UV) run --python 3.11 --package osii-model-provider-bridge python -m uvicorn app.main:app --app-dir services/model-provider-bridge --host 127.0.0.1 --port 8095 --reload

dev-ocr-host:
	cd ai-ready-tool-shelf/osii-tesseract && ENABLE_DEMO=true $(UV) run --no-project --python 3.11 --with-requirements requirements.txt python -m uvicorn app.main:app --host 127.0.0.1 --port 8080

# Run only Apache Tika in a container. Use this in a second terminal alongside
# `make dev` when the editable application stack should remain on the host.
dev-tika:
	$(COMPOSE) --profile ocr up -d tika

# Hybrid development for deployment-parity extraction: Tika and Tesseract use
# containers while the application services continue to run from source.
dev-containers: dev-services
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

# Explicit opt-in for registries whose TLS certificates cannot be verified.
# This affects image pulls/builds only and is intentionally Podman-specific.
dev-containers-insecure:
	$(COMPOSE) --podman-pull-args=--tls-verify=false --podman-build-args=--tls-verify=false --profile ocr up -d tika tesseract
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

dev-services:
	$(COMPOSE) --profile ocr up -d tika tesseract

# Start the normal integrated stack from existing images, without rebuilding.
run:
	$(COMPOSE) up --no-build --pull missing local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker dashboard

dev-examples: dev-services
	$(COMPOSE) --profile examples up -d --build table-pdf-enricher
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py --examples

# Rebuild and run the deployment-style container stack.
containers-dev: build
	$(COMPOSE) --profile agents --profile ocr up local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker mcp dashboard tika tesseract

dev-all: build
	$(COMPOSE) --profile examples --profile agents --profile ocr up

down:
	$(COMPOSE) --profile examples --profile agents --profile ocr down

logs:
	$(COMPOSE) logs -f

test:
	$(UV) sync --python 3.11 --package osii --extra dev
	$(UV) run --python 3.11 --package osii --extra dev python -m pytest ai-ready-ingest/tests
	$(UV) sync --python 3.11 --package osii-processor-sdk --extra dev
	$(UV) run --python 3.11 --package osii-processor-sdk --extra dev python -m pytest packages/osii-processor-sdk/tests
	cd services/local-extractor && $(UV) run --python 3.11 --package osii-local-extractor --extra dev python -m pytest tests
	cd services/local-synthesizer && $(UV) run --python 3.11 --package osii-local-synthesizer --extra dev python -m pytest tests
	cd services/local-embedder && $(UV) run --python 3.11 --package osii-local-embedder --extra dev python -m pytest tests
	cd services/local-enricher && $(UV) run --python 3.11 --package osii-local-enricher --extra dev python -m pytest tests
	cd services/model-provider-bridge && $(UV) run --python 3.11 --package osii-model-provider-bridge --extra dev python -m pytest tests
	$(UV) run --no-project --python 3.11 --with pytest --with 'uvicorn[standard]' python -m pytest services/baseline-processors/tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

# Build each distinct release image once. API/worker/chat share core; all five
# baseline processor services share one selectable-command image.
build: build-release
	$(COMPOSE) --profile examples --profile agents --profile ocr build mcp table-pdf-enricher tesseract

build-release:
	$(COMPOSE) build api dashboard local-extractor

push-release:
	@if echo "$(OSII_IMAGE_PREFIX)" | grep -q '^localhost/'; then echo "Set OSII_IMAGE_PREFIX to a registry path such as quay.io/your-org/osii."; exit 2; fi
	$(COMPOSE) push api dashboard local-extractor

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
