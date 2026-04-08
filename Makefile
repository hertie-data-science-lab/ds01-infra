# DS01 Infrastructure — Development Tasks
# Run `make help` to see available targets.
# CI mirror: `make check` runs the same checks as the PR CI pipeline.

SHELL := /bin/bash
.DEFAULT_GOAL := help

SH_FILES := $(shell find scripts/ -name '*.sh' -not -path '*/aime-ml-containers/*' -not -path '*__pycache__*' 2>/dev/null)
SHFMT_FLAGS := -i 4 -ci -s

.PHONY: help lint lint-python lint-shell fmt fmt-python fmt-shell test test-all check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Linting (check only) ─────────────────────────────────────────────

lint: lint-python lint-shell ## Run all linters

lint-python: ## Ruff format check + lint
	ruff format --check .
	ruff check .

lint-shell: ## shfmt check + shellcheck
	shfmt -d $(SHFMT_FLAGS) $(SH_FILES)
	shellcheck -x $(SH_FILES)

# ── Formatting (auto-fix) ────────────────────────────────────────────

fmt: fmt-python fmt-shell ## Auto-format all code

fmt-python: ## Ruff format + fix
	ruff format .
	ruff check --fix .

fmt-shell: ## shfmt write
	shfmt -w $(SHFMT_FLAGS) $(SH_FILES)

# ── Testing ───────────────────────────────────────────────────────────

test: ## Run unit + integration tests (excludes system)
	cd testing && python -m pytest . -m "not system" -v --tb=short

test-all: ## Run all tests including system (requires sudo + GPU)
	cd testing && sudo python -m pytest . -v --tb=short

# ── CI mirror ─────────────────────────────────────────────────────────

check: lint test ## Run full CI check locally (lint + test)
