# One supported workstation workflow: source services on the host.
UV ?= uv
OSII_PYTHON_VERSION ?= 3.12
ENV_FILE ?= .env
export UV_PROJECT_ENVIRONMENT := $(CURDIR)/osii-env
unexport VIRTUAL_ENV
.DEFAULT_GOAL := help
.PHONY: help dev demo demo-data test docs doctor

help:
	@echo "make dev        Start OSII and all Toolbox services; Ctrl+C stops them"
	@echo "make demo       Add sample data, then start the same application"
	@echo "make test       Run Core, SDK, processor, and dashboard checks"
	@echo "make docs       Check documentation"
	@echo "make doctor     Report disk usage without deleting anything"
	@echo "Configure source paths and the model endpoint in .env (optional)."
	@echo "Choose another private startup profile with ENV_FILE=.env.personal"

dev:
	OSII_STARTUP_ENV="$(ENV_FILE)" $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

demo: demo-data
	OSII_STARTUP_ENV="$(ENV_FILE)" $(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/dev_stack.py

demo-data:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with 'scikit-learn>=1.5,<2' python scripts/import_example_data.py

test:
	$(UV) sync --frozen --python $(OSII_PYTHON_VERSION) --package osii --extra rag-haystack --extra dev
	$(UV) run --frozen --python $(OSII_PYTHON_VERSION) --package osii --extra rag-haystack --extra dev python -m pytest osii-core/tests osii-core/processor-sdk/tests osii-core/rag-tests
	@for service in local-extractor local-tesseract local-synthesizer local-embedder local-enricher model-provider-bridge; do \
		$(UV) run --isolated --no-project --python $(OSII_PYTHON_VERSION) --with-editable osii-core --with-editable osii-core/services/$$service --with 'httpx>=0.27,<1' --with pytest python -m pytest osii-core/services/$$service/tests || exit $$?; \
	done
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with pytest --with 'uvicorn[standard]' python -m pytest osii-core/services/baseline-processors/tests
	cd osii-dashboard/dashboard && npm test --if-present && npm run build

docs:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/check_docs_links.py
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) --with mkdocs-material mkdocs build --strict

doctor:
	$(UV) run --no-project --python $(OSII_PYTHON_VERSION) python scripts/disk_usage.py
