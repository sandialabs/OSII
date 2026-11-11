# One supported workstation workflow: source services on the host.
UV ?= uv
OSII_PYTHON_VERSION ?= 3.12
ENV_FILE ?= .env
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
unexport VIRTUAL_ENV
.DEFAULT_GOAL := help
.PHONY: help dev demo demo-data test docs doctor

# uv needs these values in its own environment, before Python exists. Read only
# literal certificate settings; never source .env as executable shell code.
define startup_environment
@set -eu; \
osii_env_file="$(ENV_FILE)"; export OSII_STARTUP_ENV="$$osii_env_file"; \
if [ "$$osii_env_file" != .env ] && [ ! -f "$$osii_env_file" ]; then echo "Startup env file not found: $$osii_env_file" >&2; exit 2; fi; \
osii_protected=" "; \
for osii_name in UV_SYSTEM_CERTS UV_NATIVE_TLS SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE PIP_CERT NODE_EXTRA_CA_CERTS; do \
	if printenv "$$osii_name" >/dev/null; then osii_protected="$$osii_protected$$osii_name "; fi; \
done; \
if [ -f "$$osii_env_file" ]; then \
	while IFS= read -r osii_line || [ -n "$$osii_line" ]; do \
		osii_line=$$(printf '%s' "$$osii_line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
		case "$$osii_line" in export[[:space:]]*) osii_line=$${osii_line#export}; esac; \
		case "$$osii_line" in \#*|*=*) ;; *) continue ;; esac; \
		osii_name=$$(printf '%s' "$${osii_line%%=*}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
		case "$$osii_name" in UV_SYSTEM_CERTS|UV_NATIVE_TLS|SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|PIP_CERT|NODE_EXTRA_CA_CERTS) ;; *) continue ;; esac; \
		case "$$osii_protected" in *" $$osii_name "*) continue ;; esac; \
		osii_value=$$(printf '%s' "$${osii_line#*=}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//'); \
		case "$$osii_value" in \
			\"*) osii_value=$${osii_value#\"}; case "$$osii_value" in *\"*) ;; *) echo "Invalid $$osii_name in .env: missing closing quote." >&2; exit 2 ;; esac; osii_tail=$${osii_value#*\"}; osii_value=$${osii_value%%\"*} ;; \
			\'*) osii_value=$${osii_value#\'}; case "$$osii_value" in *\'*) ;; *) echo "Invalid $$osii_name in .env: missing closing quote." >&2; exit 2 ;; esac; osii_tail=$${osii_value#*\'}; osii_value=$${osii_value%%\'*} ;; \
			*) osii_tail=""; osii_value=$${osii_value%%\#*} ;; \
		esac; \
		osii_tail=$$(printf '%s' "$$osii_tail" | sed 's/^[[:space:]]*//'); \
		case "$$osii_tail" in ""|\#*) ;; *) echo "Invalid $$osii_name in .env: use one literal value with matching quotes." >&2; exit 2 ;; esac; \
		osii_value=$$(printf '%s' "$$osii_value" | sed 's/[[:space:]]*$$//'); \
		export "$$osii_name=$$osii_value"; \
	done < "$$osii_env_file"; \
fi; \
if [ -n "$${SSL_CERT_FILE:-}" ]; then \
	if [ ! -r "$$SSL_CERT_FILE" ] || ! grep -q '^-----BEGIN CERTIFICATE-----' "$$SSL_CERT_FILE"; then \
		echo "SSL_CERT_FILE must point to a readable PEM CA bundle. Use an absolute path; DER .crt files must be exported as PEM." >&2; exit 2; \
	fi; \
fi;
endef

help:
	@echo "make dev        Start OSII and all Toolbox services; Ctrl+C stops them"
	@echo "make demo       Add sample data, then start the same application"
	@echo "make test       Run Core, SDK, processor, and dashboard checks"
	@echo "make docs       Check documentation"
	@echo "make doctor     Report disk usage without deleting anything"
	@echo "Configure source paths and the model endpoint in .env (optional)."
	@echo "Choose another private startup profile with ENV_FILE=.env.personal"

dev:
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

demo: demo-data
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

demo-data:
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with 'scikit-learn>=1.5,<2' python scripts/import_example_data.py

test:
	$(startup_environment) $(UV) sync --frozen --python $(OSII_PYTHON_VERSION) --package osii --extra rag-haystack --extra dev
	$(startup_environment) $(UV) run --frozen --python $(OSII_PYTHON_VERSION) --package osii --extra rag-haystack --extra dev python -m pytest osii-core/tests osii-core/processor-sdk/tests osii-core/rag-tests
	$(startup_environment) for service in local-extractor local-tesseract local-synthesizer local-embedder local-enricher model-provider-bridge; do \
		$(UV) run --isolated --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core --with-editable osii-core/services/$$service --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/$$service/tests || exit $$?; \
	done
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with pytest --with 'uvicorn[standard]' python -m pytest osii-core/services/baseline-processors/tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

docs:
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/check_docs_links.py
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with mkdocs-material mkdocs build --strict

doctor:
	$(startup_environment) $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/disk_usage.py
