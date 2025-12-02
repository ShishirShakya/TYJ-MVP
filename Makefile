.PHONY: help install test lint format type-check security-check clean run-dev setup

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies using uv
	uv sync

setup: install ## Set up development environment
	@echo "Setting up development environment..."
	@if [ ! -f .env ]; then \
		echo "Creating .env file from template..."; \
		cp .env.example .env 2>/dev/null || echo "# Add your environment variables here" > .env; \
	fi
	@echo "Development environment ready!"

test: ## Run tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage (no threshold)
	uv run pytest tests/ --cov=exam --cov=shared --cov=dash --cov=prof --cov-report=html --cov-report=term

test-cov-threshold: ## Run tests with coverage threshold (fails if < 70%)
	uv run pytest tests/ --cov=exam --cov=shared --cov=dash --cov=prof --cov-report=html --cov-report=term --cov-fail-under=70

lint: ## Run linting (ruff)
	uv run ruff check .

format: ## Format code (ruff)
	uv run ruff format .

format-check: ## Check code formatting without modifying
	uv run ruff format --check .

type-check: ## Run type checking (mypy)
	uv run mypy . --ignore-missing-imports

security-check: ## Run security checks (bandit, safety)
	uv run bandit -r exam/ shared/ dash/ prof/ -ll
	uv run safety check --file requirements.txt

check: lint format-check type-check ## Run all checks (lint, format, type)

clean: ## Clean temporary files
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete

run-dev: ## Run development server (placeholder - adjust for your setup)
	@echo "Run your Gradio notebooks or FastAPI app manually"
	@echo "For exam.ipynb: jupyter notebook exam.ipynb"
	@echo "For dash.ipynb: jupyter notebook dash.ipynb"
	@echo "For prof.ipynb: jupyter notebook prof.ipynb"

pre-commit: ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

ci: install test lint format-check type-check pre-commit ## Run CI checks locally

