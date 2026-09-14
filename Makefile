# Podman is the default local container runtime. Override per invocation for
# Docker Desktop, for example: make COMPOSE='docker compose' run
COMPOSE ?= podman-compose
UV ?= uv
OSII_IMAGE_PREFIX ?= localhost/osii
OSII_IMAGE_TAG ?= latest
OSII_BASE_IMAGE ?= registry.access.redhat.com/ubi9/ubi:latest
OSII_PYTHON_VERSION ?= 3.12
OSII_CA_BUNDLE ?=
SHARED_DRIVE_PATH ?=
SHARED_DRIVE_DATA ?= ./osii-data/shared-drive
DISABLE_CONTAINER_PROXIES ?= false
PROXY_ENVIRONMENT_VARIABLES := HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY http_proxy https_proxy ftp_proxy all_proxy

ifeq ($(DISABLE_CONTAINER_PROXIES),true)
PODMAN_PROXY_BUILD_ARGUMENTS := --podman-build-args='--http-proxy=false $(foreach variable,$(PROXY_ENVIRONMENT_VARIABLES),--env $(variable)= --unsetenv $(variable))'
PODMAN_PROXY_RUN_ARGUMENTS := --podman-run-args='--http-proxy=false $(foreach variable,$(PROXY_ENVIRONMENT_VARIABLES),--env $(variable)=)'
else ifneq ($(DISABLE_CONTAINER_PROXIES),false)
$(error DISABLE_CONTAINER_PROXIES must be true or false)
endif

ifneq ($(strip $(OSII_CA_BUNDLE)),)
OSII_CA_BUNDLE_SHA256 := $(shell if command -v sha256sum >/dev/null 2>&1; then sha256sum "$(OSII_CA_BUNDLE)"; else shasum -a 256 "$(OSII_CA_BUNDLE)"; fi 2>/dev/null | awk '{print $$1}')
PODMAN_CA_BUILD_ARGUMENTS := --podman-build-args='--secret=id=osii_ca_bundle,src="$(OSII_CA_BUNDLE)" --mount=type=secret,id=osii_ca_bundle --build-arg OSII_CA_BUNDLE_SHA256=$(OSII_CA_BUNDLE_SHA256) --env SSL_CERT_FILE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem --env REQUESTS_CA_BUNDLE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem --env CURL_CA_BUNDLE=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem --env PIP_CERT=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem --env UV_NATIVE_TLS=true --env NODE_EXTRA_CA_CERTS=/etc/pki/ca-trust/source/anchors/osii-local-ca-bundle.pem'
endif
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
export OSII_IMAGE_PREFIX OSII_IMAGE_TAG OSII_BASE_IMAGE OSII_PYTHON_VERSION
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

define validate_ca_bundle
	@if [ -n "$(OSII_CA_BUNDLE)" ]; then \
		case "$(COMPOSE)" in \
			*podman-compose*) ;; \
			*) echo "OSII_CA_BUNDLE requires podman-compose so the certificate file can be passed as a build secret."; exit 2 ;; \
		esac; \
		if [ -z "$(OSII_CA_BUNDLE_SHA256)" ]; then echo "Unable to read OSII_CA_BUNDLE: $(OSII_CA_BUNDLE)"; exit 2; fi; \
		$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/validate_ca_bundle.py "$(OSII_CA_BUNDLE)"; \
	fi
endef

define validate_shared_drive
	@if [ -z "$(SHARED_DRIVE_PATH)" ]; then echo "Set SHARED_DRIVE_PATH to an already mounted SMB/shared-drive folder."; exit 2; fi
	@if [ ! -d "$(SHARED_DRIVE_PATH)" ] || [ ! -r "$(SHARED_DRIVE_PATH)" ]; then echo "Shared drive is unavailable or unreadable: $(SHARED_DRIVE_PATH)"; exit 2; fi
endef

.PHONY: help dev dev-shared demo demo-data run run-shared build push-release publish-multiarch down logs test docs doctor

help:
	@echo "OSII startup commands"
	@echo "  make demo       Install the example files and start OSII"
	@echo "  make dev        Start OSII with files already in osii-data/source"
	@echo "  make dev-shared Start OSII against an already mounted shared drive"
	@echo "  make run        Start previously built container images"
	@echo "  make run-shared Start images with an already mounted shared drive"
	@echo "  make publish-multiarch Build and push Linux AMD64 + ARM64 release manifests"
	@echo "  make down       Stop the container deployment"
	@echo "  make doctor     Report disk usage; never deletes files"
	@echo ""
	@echo "Normal source development needs only 'make demo' or 'make dev'. Optional AI,"
	@echo "Tika, and non-bundled Toolbox services are connected from the Setup page."
	@echo "For direct-network Podman containers, append DISABLE_CONTAINER_PROXIES=true."
	@echo "To add local corporate trust, append OSII_CA_BUNDLE=/path/to/roots.pem."

# Default development path: API (including chat), worker, MCP, dashboard, and extraction
# all run from source on the host. Setup can start optional Tika when a container
# runtime is available; the core development stack does not require one.
dev:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

# Shared-drive credentials and mounting remain owned by the operating system.
# OSII reads that mounted path and keeps its writable sidecar data locally.
dev-shared:
	$(validate_shared_drive)
	OSII_SOURCE_DIR="$(SHARED_DRIVE_PATH)" OSII_RUNTIME_DIR="$(SHARED_DRIVE_DATA)" OSII_SOURCE_KIND=shared $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

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
	$(COMPOSE) $(PODMAN_PROXY_RUN_ARGUMENTS) up -d --no-build --pull missing tesseract local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker dashboard

run-shared:
	$(validate_shared_drive)
	$(require_podman_proxy_control)
	OSII_SOURCE_DIR="$(SHARED_DRIVE_PATH)" OSII_SOURCE_KIND=shared $(COMPOSE) $(PODMAN_PROXY_RUN_ARGUMENTS) up -d --no-build --pull missing tesseract local-extractor local-synthesizer local-embedder local-enricher model-provider-bridge api worker dashboard

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

# Build the four publishable release images. API and worker share core; the
# baseline processor services share one selectable-command image; the bundled,
# default-swappable Tesseract OCR extractor keeps its independent image.
build:
	$(require_podman_proxy_control)
	$(validate_ca_bundle)
	@trap 'find "$(CURDIR)" -type f -name "podman-build-secret-*" -delete' EXIT HUP INT TERM; \
		$(COMPOSE) $(PODMAN_CA_BUILD_ARGUMENTS) $(PODMAN_PROXY_BUILD_ARGUMENTS) build api dashboard local-extractor tesseract

push-release:
	@if echo "$(OSII_IMAGE_PREFIX)" | grep -q '^localhost/'; then echo "Set OSII_IMAGE_PREFIX to a registry path such as quay.io/your-org/osii."; exit 2; fi
	$(COMPOSE) push api dashboard local-extractor tesseract

publish-multiarch:
	@if echo "$(OSII_IMAGE_PREFIX)" | grep -q '^localhost/'; then echo "Set OSII_IMAGE_PREFIX to your Quay registry path."; exit 2; fi
	@if [ "$(OSII_IMAGE_TAG)" = "latest" ]; then echo "Set OSII_IMAGE_TAG to an immutable release version."; exit 2; fi
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/publish_multiarch.py \
		--image-prefix "$(OSII_IMAGE_PREFIX)" \
		--image-tag "$(OSII_IMAGE_TAG)" \
		--base-image "$(OSII_BASE_IMAGE)" \
		--python-version "$(OSII_PYTHON_VERSION)" \
		$(if $(strip $(OSII_CA_BUNDLE)),--ca-bundle "$(OSII_CA_BUNDLE)") \
		$(if $(filter true,$(DISABLE_CONTAINER_PROXIES)),--disable-container-proxies)

docs:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/check_docs_links.py
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with mkdocs-material mkdocs build --strict

doctor:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/disk_usage.py
