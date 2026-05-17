SHELL := /usr/bin/env bash -O globstar

##@ Help

.PHONY: help
help: ## Display this help message
	@echo "Available targets:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?##"; section = ""} \
			/^##@/ { \
					if (section != "") print ""; \
					section = substr($$0, 5); \
					printf "\033[1m%s\033[0m\n", section \
			} \
			/^[a-zA-Z_0-9\/-]+:.*?##/ { \
					if (section != "") { \
							printf "\033[36m%-30s\033[0m %s\n", $$1, $$2 \
					} \
			}' $(MAKEFILE_LIST)

##@@ Local - Development

.PHONY: clean
clean: ## Clean project build artifacts
	rm -rf \
		.mypy_cache \
		htmlcov \
		test-results \
		**/*.pyc \
		**/__pycache__

.PHONY: fix
fix: ## Run auto-fixing for linting errors using ruff
	poetry run ruff format
	poetry run ruff check --preview --fix

.PHONY: lint
lint: ## Run linting checks using ruff and mypy
	poetry run ruff check --preview
	poetry run mypy .

.PHONY: all
all: ## Helper target to run all checks and tests
	make clean
	make fix
	make lint
	make test

.PHONY: install
install: ## Install project dependencies using poetry
	poetry install

##@ Local - Testing

.PHONY: test
test: ## Run tests using pytest
	poetry run pytest tests --junit-xml=test-results/pytest/results.xml -s -vv

##@ Version

BUMP ?= patch

.PHONY: version
version: ## Bump version (default: patch)
	poetry version $(BUMP)
	make install

.PHONY: version/minor
version/minor: ## Bump minor version
	make version BUMP=minor

.PHONY: version/major:
version/major: ## Bump major version
	make version BUMP=major

.PHONY: version/push:
version/push: ## Bump version and push to remote repository
	make version
	git add pyproject.toml
	git commit -m "chore: auto-bump version"
	git push
