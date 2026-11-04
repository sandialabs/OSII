# Server development: explicit PostgreSQL configuration, no file-store fallback.
UV ?= uv
OSII_PYTHON_VERSION ?= 3.12
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/.venv
unexport VIRTUAL_ENV
.DEFAULT_GOAL := help
.PHONY: help dev demo demo-data test docs doctor

help:
	@echo "make dev        Start configured local PostgreSQL and OSII; Ctrl+C stops OSII"
	@echo "make test       Run Core, SDK, processor, and dashboard checks"
	@echo "make docs       Check documentation"
	@echo "make doctor     Report disk usage without deleting anything"
	@echo "Configure PostgreSQL, source paths, and the model endpoint in .env."

dev:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

demo:
	@echo "Server datasets are provisioned by administrators; use make dev."

demo-data:
	@echo "Server datasets are provisioned by administrators; no files imported."

test:
	$(UV) sync --frozen --python $(OSII_PYTHON_VERSION) --package osii --extra server --extra dev
	$(UV) run --frozen --package osii --extra server --extra dev python -m pytest osii-core/server-tests osii-core/processor-sdk/tests -q
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

docs:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/check_docs_links.py
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with mkdocs-material mkdocs build --strict

doctor:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/disk_usage.py
