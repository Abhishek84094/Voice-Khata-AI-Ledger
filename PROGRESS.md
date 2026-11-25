# Progress Log — Voice Khata

## Current phase: 0 — Project setup and decisions

### Done (with evidence: command output or probe result)
- Initialized isolated git repository and folder structure matching §3.3.
- Installed Python 3.12 (CPython 3.12.16) via `uv` and provisioned virtual environment `.venv`.
- Configured `.gitignore`, `.env.example`, `.env` (holding user-supplied Sarvam and Groq API keys, generated 32-byte AES `LEDGER_KEY`), and `docker-compose.yml` for PostgreSQL 16.
- Scaffolded `backend/app` with Pydantic settings, FastAPI application, and `/healthz` endpoint.
- Created unit test `backend/tests/unit/test_healthz.py` verifying `/healthz` returns 200 with `status="ok"`.
- Built cross-platform gate runner `scripts/check.py`, `Makefile`, and GitHub Actions CI workflow (`.github/workflows/ci.yml`).
- Formatted and linted evaluation files in `eval/` (`eval_nlu.py`, `probe_pipeline.py`).
- Created `docs/decisions.md`.
- **Gate Check Evidence** (`python scripts/check.py` output):
  ```
  --- [GATE] Running: ruff format check ---
  Command: ...\.venv\Scripts\python.exe -m ruff format --check .
  [GATE PASSED] ruff format check

  --- [GATE] Running: ruff lint check ---
  Command: ...\.venv\Scripts\python.exe -m ruff check .
  [GATE PASSED] ruff lint check

  --- [GATE] Running: mypy strict ---
  Command: ...\.venv\Scripts\python.exe -m mypy --strict backend/app
  [GATE PASSED] mypy strict

  --- [GATE] Running: pytest coverage ---
  Command: ...\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=85 backend/tests
  [GATE PASSED] pytest coverage (100% coverage, 1 passed)

  --- [GATE] Running: bandit security scan ---
  Command: ...\.venv\Scripts\python.exe -m bandit -q -r backend/app -c pyproject.toml
  [GATE PASSED] bandit security scan (0 issues)

  --- [GATE] Running: pip-audit dependency vulnerability check ---
  Command: ...\.venv\Scripts\python.exe -m pip_audit
  [GATE PASSED] pip-audit dependency vulnerability check (No known vulnerabilities found)

  ==========================================
  ALL GATE CHECKS PASSED SUCCESSFULLY (GREEN)
  ==========================================
  ```

### Next
- Proceed to **Phase 1 — Provider bake-off and latency spike**:
  - Verify and document Sarvam AI and Groq platform specifications (endpoints, auth, streaming protocol, latency budgets) in `docs/platform-notes.md`.
  - Benchmark live latency and streaming capabilities of candidate providers.
  - Generate reading script from `eval/golden_utterances.json` for recording verification clips.

### Decisions (with reason; chosen providers with measured numbers)
- **Python Runtime**: Python 3.12 via `uv` for fast, reproducible environments.
- **Speech & LLM Providers**: Sarvam AI selected for speech recognition (STT) and synthesis (TTS); Groq selected for low-latency JSON LLM fallback.
- **Language & Script Policy**: Support all Sarvam AI supported Indian languages; dual-script policy (store and index both Latin search keys and native scripts).
- **Security & Secrets**: Strict gitignore for `.env` and `.key`; AES-256-GCM encryption key generated at 32-bytes; no secrets logged.
- **Cross-Platform Gate**: `scripts/check.py` runner ensures consistent validation on Windows and Linux CI.

### Open questions for the human
- None for Phase 0.

### Metrics: tests 1 · coverage 100% · golden-set results: pending Phase 1/2

### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
- Healthz test execution: 2.30s total harness overhead. Real live latency measurements begin in Phase 1.
