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

## 4. Providers & AI Strategy (Phase 1 Bake-Off Results)

### 4.1 Speech-to-Text (STT)
- **Selected Provider**: Sarvam AI (`saaras:v3`).
- **Reason**: Native support for Indian languages and code-mixed Hindi/English. `saarika:v2` is deprecated by Sarvam; `saaras:v3` is the active, verified production model.
- **Measured Latency**:
  - P50: **227.4 ms**
  - P95: **702.7 ms**
  - Mean: **330.5 ms**
- **Discovered Nuance**: Returns Devanagari numerals (`३४०` instead of `340`) for Hindi speech. Normalizer must map `[०-९]` to standard digits.

### 4.2 Text-to-Speech (TTS)
- **Selected Provider**: Sarvam AI (`bulbul:v4-flash`, fallback: `bulbul:v3`).
- **Reason**: Sub-second conversational generation in Indian accents.
- **Measured Latency (`bulbul:v4-flash`)**:
  - P50: **1040.0 ms**
  - P95: **1321.5 ms**
  - Mean: **1058.7 ms**
- **Caching Strategy**: Pre-synthesize and locally cache fixed confirmation audio ("हो गया", "लिख लिया", etc.) to start spoken confirmation in < 50 ms.

### 4.3 LLM Client (Slow-Path Fallback)
- **Selected Provider**: Groq running `qwen/qwen3.8-27b` with JSON mode at temperature 0.
- **Reason**: Ultra-low latency JSON generation beats all standard cloud LLM endpoints.
- **Measured Latency**:
  - P50: **222.9 ms**
  - P95: **889.0 ms**
  - Min: **178.6 ms**
  - JSON validity rate: **100.0%**

## 5. Reliability & Truthfulness
- **Truthful Confirmations**: UI and TTS confirmations are issued only after database commit completes.
- **Deterministic Derivations**: All customer balances and promise allocations are derived from append-only events, backed by a single-transaction balance cache table.
