# Progress Log — Voice Khata

## Current phase: 3 — Storage, ledger, caches (COMPLETED)

### Done (with evidence: command output or probe result)
- **Field-level AES-256-GCM encryption** (`backend/app/storage/encryption.py`):
  - Encrypts customer display names, transaction amounts (paise), and notes at rest using 32-byte `LEDGER_KEY`.
  - Format: `base64(12-byte IV + ciphertext + 16-byte tag)`.
  - Verified plaintext absence via raw PostgreSQL query bypass (`test_encryption_at_rest_plaintext_check`).
- **In-process per-shop customer cache** (`backend/app/storage/customer_cache.py`):
  - Resolves Latin transliterated search keys (e.g. `ramesh`, `sharma`) to customer IDs and primary display names.
  - Sub-millisecond lookup across 5,000 customers (P95 < 1.0 ms).
  - Synchronous / thread-safe mutation with per-shop tenant isolation.
- **SQLAlchemy 2 async schema & models** (`backend/app/storage/models.py`):
  - `shops`, `users`, `customers`, `ledger_events`, `customer_balances`, `promises`, `audit_log`.
  - Immutable append-only ledger events with SHA-256 integrity hash chaining (`prev_event_hash` -> `hash`).
  - Integer paise for all monetary columns (no floats).
- **Atomic ledger service** (`backend/app/storage/ledger_service.py`):
  - Single-transaction commit executing event append + balance cache update + audit record atomically.
  - Idempotency key deduplication (prevents double commits on network retries).
  - Cache-first customer resolution with auto-provisioning.
  - Audit logging for all ledger writes.
  - Data privacy / GDPR-style export (`export_all_data`) and purge (`delete_all_data`).
- **Integration Tests against real PostgreSQL 16** (`backend/tests/integration/test_ledger_service.py`):
  - `test_single_transaction_commit_and_balance_cache`: Invariant check proving balance cache == replay of event log.
  - `test_idempotent_duplicate_handling`: Proves duplicate idempotency keys return existing result without balance doubling.
  - `test_encryption_at_rest_plaintext_check`: Raw asyncpg query verifies no customer names, amounts, or notes appear in plaintext in the database.
  - `test_export_and_delete_all`: Complete shop data export and zero-trace purge.
  - `test_commit_latency_benchmark`: Empirical pooled DB commit benchmark:
    - **P50: 10.35 ms, P95: 15.24 ms, Min: 6.50 ms** (50 commits, budget ≤ 30 ms).
- **Gate Status (`python scripts/check.py`)**:
  - `ruff format`: PASSED (41 files)
  - `ruff lint`: PASSED
  - `mypy --strict`: PASSED (17 source files)
  - `pytest coverage`: **93.31% overall** (51 passed, required ≥ 85%)
  - `bandit`: PASSED (0 security issues)
  - `pip-audit`: PASSED (0 known vulnerabilities)

### Next
- Proceed to **Phase 4 — Voice session core**:
  - WebSocket endpoint `/ws/voice` accepting binary PCM16 audio chunks and JSON client control frames (`start`, `commit`, `cancel`).
  - Pre-warmed STT stream / session state management per shop session.
  - Fast-path / slow-path state machine:
    - Fast path: rules parser confident → single-transaction ledger commit → immediate UI `saved` JSON event with new balance → dynamic or pre-cached acknowledgment TTS audio.
    - Slow path: rules parser ambiguous → Groq LLM completion → clarification / read-back question.
  - Empirical latency measurement probe (`scripts/probe_pipeline.py`) validating speed budgets (§4).
  - Minimal browser test harness (`frontend/index.html`) displaying mic recording, live transcript, saved card, and timing breakdowns.

### Decisions (with reason; chosen providers with measured numbers)
- **Persistent Connection Pooling**: PostgreSQL on Docker/WSL2 adds ~8 ms TCP handshake latency over loopback. Utilizing persistent pooled async engines (`async_sessionmaker` with `pool_size=10, max_overflow=20`) dropped DB commit latency from 46 ms down to **P50 = 10.35 ms, P95 = 15.24 ms**, comfortably beating the ≤ 30 ms budget.
- **Field-Level Encryption**: Standard AES-256-GCM at the application tier guarantees zero plaintext leakage even in raw DB dumps or log exports, satisfying tenant privacy constraints without database plugin dependencies.
- **Balance Cache Replay Invariant**: `customer_balances` is strictly a performance projection; `replay_customer_balance()` validates that the event log is the single source of truth.

### Open questions for the human
- None for Phase 3.

### Metrics: tests 51 · coverage 93.31% · golden-set results: 59/59 (100.0%)

### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
- **Rules Parse Latency**: p50 = 0.292 ms, p95 = 0.955 ms
- **DB Commit Latency**: **p50 = 10.35 ms, p95 = 15.24 ms** (measured on warm connection pool)
- **STT Latency (Sarvam saaras:v3)**: p50 = 227.4 ms, p95 = 702.7 ms
- **LLM Latency (Groq qwen/qwen3.8-27b)**: p50 = 222.9 ms, p95 = 889.0 ms
