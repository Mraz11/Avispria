.PHONY: setup fmt lint type test check ui

setup:
	uv sync
	uv run pre-commit install

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run python scripts/check_file_length.py --root src

type:
	uv run mypy src/avispria/core

test:
	uv run pytest

check:
	uv run python scripts/check.py

ui:
	@echo "UI not implemented yet (Phase 1: NiceGUI)."
