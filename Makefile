# Cross-platform Makefile for Voice Khata
PYTHON ?= python

.PHONY: help check test lint format perf run-db

help:
	@echo "Voice Khata targets:"
	@echo "  make check     - Run full gate check (ruff, mypy, pytest, bandit, pip-audit, gitleaks)"
	@echo "  make test      - Run unit and integration tests with coverage"
	@echo "  make lint      - Run ruff lint and format check"
	@echo "  make format    - Autoformat code with ruff"
	@echo "  make run-db    - Start Postgres in docker"

check:
	$(PYTHON) scripts/check.py

test:
	$(PYTHON) -m pytest -q --cov=app --cov-fail-under=85 backend/tests

lint:
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy --strict backend/app

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

run-db:
	docker compose up -d db
