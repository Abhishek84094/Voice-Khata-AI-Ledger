# Architecture and Project Decisions

## 1. Runtime & Environment
- **Python**: 3.12 (CPython) managed via `uv`.
- **Operating System**: Cross-platform support (Windows host development + Linux CI/Docker).
- **Execution Gate**: `scripts/check.py` provides cross-platform execution of ruff, mypy, pytest with coverage, bandit, and pip-audit, wrapped by `Makefile` (`PYTHON ?= python`).

## 2. Framework & API
- **Web Framework**: FastAPI with `orjson` default response class for high serialization speed.
- **Async Engine**: Fully async endpoints; `httptools` on Windows and `uvloop` on Linux/Docker.
- **Configuration**: Pydantic `BaseSettings` reading from `.env`.

## 3. Storage & Encryption
- **Database**: PostgreSQL 16 via SQLAlchemy 2 async + `asyncpg`. No SQLite allowed.
- **Isolation**: Strict per-shop scoping on all database tables and queries.
- **Encryption**: AES-256-GCM field-level encryption for customer names, notes, and transaction amounts at rest (`LEDGER_KEY`).
- **Money Representation**: Strict integer paise. Floats for money are prohibited.

## 4. Providers & AI Strategy
- **Speech (STT / TTS)**: Sarvam AI for Indian language speech recognition and text-to-speech. Candidate bake-off and latency benchmarks in Phase 1.
- **LLM**: Groq (small, fast models at temperature 0 with strict JSON schema output) for the slow-path fallback.
- **Language & Scripts Policy**: Support all Sarvam AI supported Indian languages. Store and index both native script (Devanagari, etc.) and Latin transliteration/phonetic keys for resilient name search.

## 5. Reliability & Truthfulness
- **Truthful Confirmations**: UI and TTS confirmations are issued only after database commit completes.
- **Deterministic Derivations**: All customer balances and promise allocations are derived from append-only events, backed by a single-transaction balance cache table.
