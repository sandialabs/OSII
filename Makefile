# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' run
COMPOSE ?= podman-compose
UV ?= uv
OSII_IMAGE_PREFIX ?= localhost/osii
OSII_IMAGE_TAG ?= latest
OSII_BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi:latest
OSII_TESSERACT_BASE_IMAGE ?= registry.fedoraproject.org/fedora:latest
OSII_PYTHON_VERSION ?= 3.12
DISABLE_CONTAINER_PROXIES ?= false
PROXY_ENVIRONMENT_VARIABLES := HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY http_proxy https_proxy ftp_proxy all_proxy

ifeq ($(DISABLE_CONTAINER_PROXIES),true)
PODMAN_PROXY_BUILD_ARGUMENTS := --podman-build-args='--http-proxy=false $(foreach variable,$(PROXY_ENVIRONMENT_VARIABLES),--env $(variable)= --unsetenv $(variable))'
PODMAN_PROXY_RUN_ARGUMENTS := --podman-run-args='--http-proxy=false $(foreach variable,$(PROXY_ENVIRONMENT_VARIABLES),--env $(variable)=)'
else ifneq ($(DISABLE_CONTAINER_PROXIES),false)
$(error DISABLE_CONTAINER_PROXIES must be true or false)
endif
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
export OSII_IMAGE_PREFIX OSII_IMAGE_TAG OSII_BASE_IMAGE OSII_TESSERACT_BASE_IMAGE OSII_PYTHON_VERSION
export OSII_COMPOSE_COMMAND := $(COMPOSE)
unexport VIRTUAL_ENV

define require_podman_proxy_control
	@if [ "$(DISABLE_CONTAINER_PROXIES)" = "true" ]; then \
		case "$(COMPOSE)" in \
			*podman-compose*) ;; \
			*) echo "DISABLE_CONTAINER_PROXIES=true requires podman-compose; Docker cannot guarantee removal of proxy settings inherited from a custom base image."; exit 2 ;; \
		esac; \
	fi
endef

.PHONY: help dev demo demo-data run build push-release down logs test docs doctor

help:
	@echo "OSII startup commands"
	@echo "  make demo       Install the example files and start OSII"
	@echo "  make dev        Start OSII with files already in osii-data/source"
	@echo "  make run        Start previously built container images"
	@echo "  make down       Stop the container deployment"
	@echo "  make doctor     Report disk usage; never deletes files"
	@echo ""
	@echo "Normal use needs only 'make demo' or 'make dev'. Optional AI and OCR"
	@echo "services are connected or started from the Setup page after launch."
	@echo "For direct-network Podman containers, append DISABLE_CONTAINER_PROXIES=true."

# Default development path: API (including chat), worker, MCP, dashboard, and extraction
# all run from source on the host. Setup can start optional Tika when a container
# runtime is available; the core development stack does not require one.
dev:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

# One-command first run: install the public examples, then start the same
# complete baseline stack as `make dev`.
demo: demo-data
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

# Install the small public demo corpus without retaining download archives.
demo-data:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with 'scikit-learn>=1.5,<2' python scripts/import_example_data.py

# Start the normal integrated stack from existing images, without rebuilding.
run:
	$(require_podman_proxy_control)
	$(COMPOSE) $(PODMAN_PROXY_RUN_ARGUMENTS) up --no-build --pull missing tesseract local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker dashboard

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

test:
	$(UV) sync --python $(OSII_PYTHON_VERSION) --package osii --extra dev
	$(UV) run --python $(OSII_PYTHON_VERSION) --package osii --extra dev python -m pytest osii-core/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with pytest python -m pytest osii-core/processor-sdk/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with-editable osii-core/services/local-extractor --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/local-extractor/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with-editable osii-core/services/local-synthesizer --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/local-synthesizer/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with-editable osii-core/services/local-embedder --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/local-embedder/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with-editable osii-core/services/local-enricher --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/local-enricher/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core/processor-sdk --with-editable osii-core/services/model-provider-bridge --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/model-provider-bridge/tests
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with pytest --with 'uvicorn[standard]' python -m pytest osii-core/services/baseline-processors/tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

# Build the three publishable release images. API and worker share core; the
# baseline processor services share one selectable-command image.
build:
	$(require_podman_proxy_control)
	$(COMPOSE) $(PODMAN_PROXY_BUILD_ARGUMENTS) build api dashboard local-extractor

push-release:
	@if echo "$(OSII_IMAGE_PREFIX)" | grep -q '^localhost/'; then echo "Set OSII_IMAGE_PREFIX to a registry path such as quay.io/your-org/osii."; exit 2; fi
	$(COMPOSE) push api dashboard local-extractor

docs:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/check_docs_links.py
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with mkdocs-material mkdocs build --strict

doctor:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/disk_usage.py
