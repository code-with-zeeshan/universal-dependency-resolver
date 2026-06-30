.PHONY: setup install dev test lint typecheck clean build help

setup: install pre-commit          ## One-command setup

install:                           ## Install all dependencies
	pip install -e ".[dev,system,postgres,monitoring]"

dev:                               ## Run dev server with hot-reload
	uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

test:                              ## Run unit tests (excludes data_source)
	python -m pytest tests/unit/ -v --tb=short -k "not data_source"

test-data-sources:                 ## Run data source tests with coverage
	python -m pytest tests/unit/ -v --tb=long -k "data_source" --timeout=120 --cov=backend.data_sources --cov-report=term-missing

test-all:                          ## Run all unit tests with coverage
	python -m pytest tests/unit/ -v --tb=short --cov=backend.core --cov=backend.api --cov=backend.cli --cov=backend.settings --cov=backend.manifest_detector --cov=backend.data_sources --cov-report=term-missing --cov-fail-under=40

lint:                              ## Lint and format check
	ruff check backend/
	ruff format --check --diff backend/

typecheck:                         ## Run mypy type checking
	mypy backend --ignore-missing-imports

yamllint:                          ## Validate YAML workflow files
	yamllint .github/workflows/

clean:                             ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build: clean                       ## Build wheel and source tarball
	python -m build

help:                              ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
