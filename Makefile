# Makefile for the Art of Agents companion.
# Works on macOS and Linux. Windows developers use scripts/setup.ps1 and
# Docker. The Dockerfile is the source of truth for the CI environment.

.DEFAULT_GOAL := help

PYTHON    := .venv/bin/python
UV        := uv
DOCKER    := docker
IMAGE     := aoa-companion

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: setup
setup:  ## Create .venv with uv and install deps
	$(UV) venv --python 3.14 .venv || $(UV) venv .venv
	$(UV) pip install --python $(PYTHON) -r requirements.txt

.PHONY: install-dev
install-dev: setup  ## Install dev extras (pytest, ruff, jupyter)
	$(UV) pip install --python $(PYTHON) -e ".[dev]"

.PHONY: validate
validate:  ## Structural check: every chapter has six files
	$(PYTHON) scripts/validate_structure.py

.PHONY: test
test:  ## Run every chapter's run-eval.py
	$(PYTHON) scripts/run_all.py

.PHONY: test-one
test-one:  ## Run one chapter: make test-one CH=3
	$(PYTHON) scripts/run_all.py --chapter $(CH)

.PHONY: lint
lint:  ## Ruff lint
	$(PYTHON) -m ruff check chapters scripts

.PHONY: fmt
fmt:  ## Ruff format
	$(PYTHON) -m ruff format chapters scripts

.PHONY: docker-build
docker-build:  ## Build the CI image
	$(DOCKER) build -t $(IMAGE) .

.PHONY: docker-test
docker-test: docker-build  ## Run the full suite inside Docker
	$(DOCKER) run --rm $(IMAGE)

.PHONY: docker-shell
docker-shell: docker-build  ## Interactive shell in the CI image
	$(DOCKER) run --rm -it --entrypoint bash $(IMAGE)

.PHONY: docker-clean
docker-clean:  ## Remove the CI image
	$(DOCKER) rmi -f $(IMAGE) || true

.PHONY: clean
clean:  ## Remove caches and the venv
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

.PHONY: all
all: validate test  ## Validate structure, then run every chapter
