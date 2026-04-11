.PHONY: help install lint format test clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv sync

lint:  ## Run linter
	uv run ruff check .

format:  ## Format code
	uv run ruff format .

test:  ## Run tests
	uv run pytest tests/ -v

clean:  ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
