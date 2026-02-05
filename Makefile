# Makefile for Nano Banana Lab
# Usage: make <target>

.PHONY: help install dev lint format typecheck security test test-cov test-integration clean pre-commit run migrate

# Default target
help:
	@echo "Available targets:"
	@echo "  install          - Install production dependencies"
	@echo "  dev              - Install development dependencies"
	@echo "  lint             - Run ruff linter"
	@echo "  format           - Format code with ruff"
	@echo "  typecheck        - Run mypy type checker"
	@echo "  security         - Run bandit security scan"
	@echo "  test             - Run unit tests"
	@echo "  test-cov         - Run tests with coverage report"
	@echo "  test-integration - Run integration tests"
	@echo "  pre-commit       - Run all pre-commit hooks"
	@echo "  run              - Start development server"
	@echo "  migrate          - Run database migrations"
	@echo "  clean            - Remove build artifacts"

# ============ Installation ============

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"
	uv run pre-commit install

# ============ Code Quality ============

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy api services core database --config-file=pyproject.toml

security:
	uv run bandit -c pyproject.toml -r api services core database

# Run all checks (typecheck excluded until type annotations are complete)
check: lint format-check security

# Run all checks including type check
check-all: lint format-check typecheck security

# ============ Testing ============

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=api --cov=services --cov=core --cov-report=html --cov-report=term-missing -v

test-integration:
	uv run pytest tests/integration/ -v

test-unit:
	uv run pytest tests/unit/ -v

# ============ Pre-commit ============

pre-commit:
	uv run pre-commit run --all-files

pre-commit-update:
	uv run pre-commit autoupdate

# ============ Development ============

run:
	uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

run-prod:
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# ============ Database ============

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

migrate-new:
	@read -p "Migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

# ============ Cleanup ============

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# ============ Docker ============

docker-build:
	docker build -t nano-banana-lab .

docker-run:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f
