# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' run
COMPOSE ?= podman-compose
UV ?= uv
OSII_IMAGE_PREFIX ?= localhost/osii
OSII_IMAGE_TAG ?= latest
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
export OSII_IMAGE_PREFIX OSII_IMAGE_TAG
export OSII_COMPOSE_COMMAND := $(COMPOSE)
unexport VIRTUAL_ENV

.PHONY: dev run build push-release down logs test docs doctor

# Default development path: API (including chat), worker, MCP, dashboard, and extraction
# all run from source on the host. Setup can start optional Tika when a container
# runtime is available; the core development stack does not require one.
dev:
	$(UV) run --no-project --python 3.11 python scripts/dev_stack.py

# Start the normal integrated stack from existing images, without rebuilding.
run:
	$(COMPOSE) up --no-build --pull missing local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker dashboard

down:
	$(COMPOSE) down

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

# Build the three publishable release images. API and worker share core; the
# baseline processor services share one selectable-command image.
build:
	$(COMPOSE) build api dashboard local-extractor

push-release:
	@if echo "$(OSII_IMAGE_PREFIX)" | grep -q '^localhost/'; then echo "Set OSII_IMAGE_PREFIX to a registry path such as quay.io/your-org/osii."; exit 2; fi
	$(COMPOSE) push api dashboard local-extractor

docs:
	$(UV) run --no-project --python 3.11 python scripts/check_docs_links.py
	$(UV) run --no-project --python 3.11 --with mkdocs-material mkdocs build --strict

doctor:
	$(UV) run --no-project --python 3.11 python scripts/disk_usage.py
