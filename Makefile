.PHONY: install sync test lint fmt run docker clean

install:
	uv sync --dev

sync:
	uv sync --dev

test:
	uv run pytest -v --tb=short

lint:
	uv run ruff check src/ tests/
	uv run mypy src/

fmt:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

run:
	uv run uvicorn pulse.main:app --reload --port 8000

docker:
	docker compose up --build

clean:
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
