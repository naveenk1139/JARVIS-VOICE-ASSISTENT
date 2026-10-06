# Convenience targets. Everything here is also a plain command - see the README.
.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install install-all serve desktop ask skills doctor test lint format typecheck clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the core + web UI in editable mode
	$(PY) -m pip install -e ".[server]"

install-all: ## Install every optional extra (voice, mic, system) + dev tools
	$(PY) -m pip install -e ".[server,voice,mic,system,dev]"

serve: ## Run the browser UI and HTTP API on :8000
	$(PY) -m jarvis serve

desktop: ## Run the desktop assistant (microphone if available)
	$(PY) -m jarvis desktop

ask: ## Send one command: make ask Q="what is the weather"
	$(PY) -m jarvis ask "$(Q)"

skills: ## List registered skills
	$(PY) -m jarvis skills

doctor: ## Check optional dependencies and configuration
	$(PY) -m jarvis doctor

test: ## Run the test suite (offline)
	$(PY) -m pytest

lint: ## Lint with ruff
	ruff check jarvis tests

format: ## Auto-format with ruff
	ruff format jarvis tests
	ruff check --fix jarvis tests

typecheck: ## Static type checking (optional)
	mypy

clean: ## Remove caches and build artefacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
