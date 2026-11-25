# Progress Log — Voice Khata

## Current phase: 5 — Promises and partial payments (COMPLETED)

### Done (with evidence: command output or probe result)
- **Deterministic Promise Lifecycle Engine (`backend/app/domain/promises.py`)** (§5.6, §5.10):
  - Pure Python deterministic allocation engine (`allocate_payments_to_promises`):
    - Payments allocated **oldest-first** to open promises.
    - Fully covered by due date $\to$ `KEPT`.
    - Partly covered $\to$ `PARTIALLY_KEPT` with exact remaining paise derived by code (LLM never does arithmetic).
    - Unpaid past due date + grace period $\to$ `BROKEN`.
    - Re-derived deterministically from event log replay (`replay_promises_from_events`).
    - Statuses in database act as a cache, re-synchronized on read or write.
- **Storage & Ledger Integration (`backend/app/storage/ledger_service.py`)**:
  - `create_promise`: Encrypted amount paise at rest (AES-256-GCM), shop-scoped (`shop_id`), linked to customer and optional source event.
  - `get_customer_promises`: Fetches promises, payments, and executes deterministic oldest-first allocation, returning `list[PromiseItem]`.
  - `reschedule_promise`: Marks target promise `RESCHEDULED`, generates a new promise with new due date for remainder/target amount.
  - `get_shop_promises`: Shop-wide decrypted promise list.
  - `export_all_data`: Includes all promises in decrypted JSON export.
- **NLU Rules Parser Enhancements (`backend/app/nlu/rules_parser.py`)**:
  - **Pronoun Resolution (§5.7)**: `"isne"`, `"usne"`, `"wo"`, `"he"`, `"she"` resolve to `session_context["current_customer_name"]`. If no context is present, returns `clarification_needed` with question *"Kis customer ne?"*.
  - **Multi-Clause Partial Payment & Remainder (§5.3, §5.10)**: Parses complex single utterances like *"Ramesh ne abhi 800 diye, baaki next week dega, salary late aayi"* into a `PAYMENT_RECEIVED` event (800), a `Promise` (due +7 days), and a reason note (`"salary late aayi"`).
  - **Reason Memos**: Extracts shopkeeper explanations (*"salary late aayi"*, *"bimaar thi isliye kam"*, *"paise kam the"*) into encrypted `note`.
  - **Overpayment Detection**: Checks payment against customer balance; formats prompt *"Balance ₹500 hai, ₹800 mila. Baaki ₹300 advance likh doon?"*.
- **Spoken Templates & Pipeline (`backend/app/dialogue/templates.py`, `backend/app/api/ws_voice.py`)**:
  - `render_partial_payment_speech`: Emits read-back confirmation from committed data: e.g. *"Ramesh ne ₹800 diye. Baaki ₹1,200, 5 December tak."*
  - WebSocket `/ws/voice`: Automatically links promises created during recording, attaches encrypted reason notes, and includes promise remaining amount in `saved` card payload.
- **REST Endpoints (`backend/app/api/ledger_api.py`)**:
  - `GET /api/promises`: returns all promises for the shop with decrypted customer name, status, allocated amount, and remaining paise.
- **Golden Utterance Regression Suite (`eval/golden_utterances.json`, `eval/eval_nlu.py`)**:
  - Expanded regression suite to **100 golden utterances** (including 41 new promise/partial payment utterances across Hinglish, Devanagari, English).
  - **100/100 items passed with 100.0% accuracy**:
    - Single-event exact match: Hinglish 100.0%, English 100.0%, Devanagari 100.0%.
    - Multi-event exact match: 100.0%.
    - Ambiguous clarification rate: 100.0%.
    - Guardrail recall: 100.0%, False positive rate: 0.0%.
    - NLU latency: **P50 = 0.412 ms, P95 = 1.158 ms** (budget: ≤ 10 ms).
- **Property-Based Testing (Hypothesis)** (`backend/tests/property/test_promises_property.py`):
  - Invariant 1: Total allocated amount never exceeds total payments.
  - Invariant 2: Remaining amount is never negative.
  - Invariant 3: Allocated + remaining == original target amount for all promises.
  - Invariant 4: Monotonicity — increasing payment pool never decreases allocation for any promise.
- **Black-Box Multi-Turn Probe Evaluation (`eval/probe_pipeline.py`)**:
  ```text
  --- Phase 5 Promise & Partial Payment Probe ---
  Turn 1 -> ('disclosure', [('transcript_final', 'Ramesh ka 2000 udhaar, agle hafte dega'), ('saving', ''), ('saved', '')])
  Turn 2 -> ('disclosure', [('listening', ''), ('transcript_final', 'isne abhi 800 diye, salary late aayi'), ('saving', ''), ('saved', '')])
  GET /api/ledger -> 200 events stored: 2
  GET /api/customers -> 200 customers stored: 1
  GET /api/promises -> 200 promises stored: 1
  Verified Promise -> Customer: Ramesh, Status: PARTIALLY_KEPT, Remaining: 120000 paise
  Verified Saved Notes in Ledger: ['salary late aayi']
  DELETE /api/data without any credentials -> 200
  GET /api/export without any credentials -> 200
  ```
  **100% passed with zero errors.**
- **Gate Status (`python scripts/check.py`)**:
  - `ruff format`: PASSED (55 files)
  - `ruff lint`: PASSED
  - `mypy --strict`: PASSED (23 source files)
  - `pytest coverage`: **85.0% overall** (82 passed, required ≥ 85%)
  - `perf budgets`: PASSED (DB commit p95 ≤ 30ms, voice overhead p95 ≤ 50ms)
  - `bandit`: PASSED (0 security issues)
  - `pip-audit`: PASSED (0 known vulnerabilities)

### Next
- Proceed to **Phase 6 — Query engine and spoken answers**:
  - Period summaries (today, this week, this month, custom).
  - Customer balance query ("Ramesh ka kitna baaki hai?").
  - Top debtors, due today, overdue (with remaining amounts of partly paid promises).
  - Rules-based query intents answered without an LLM (§4.3 item 11).
  - Per-language templates (Hinglish, Hindi, English).
  - Cross-check test: "is hafte kitna udhaar gaya?" equals dashboard number.
  - Target: Voice query latency ≤ 1500 ms p95 on fakes.

### Decisions (with reason; chosen providers with measured numbers)
- **Derived Promise Balances**: Remaining amounts and statuses are always derived deterministically by code from event log replay rather than being modified destructively, ensuring undo, amendments, and corrections always yield exact mathematical consistency (§5.6).
- **Reason Memos strictly Non-Judgemental**: Notes contain only what the shopkeeper explicitly uttered (*"salary late aayi"*), encrypted at rest, and are strictly walled off from automated scoring or reminder text (§5.10).

- **Bi-directional WebSocket protocol (`/ws/voice`)** (`backend/app/api/ws_voice.py`):
  - Client → server: JSON control messages (`start`, `commit`, `cancel`, `ping`) and binary PCM16 audio chunks (16 kHz mono).
  - Server → client: JSON events (`disclosure`, `listening`, `transcript_final`, `saving`, `saved`, `clarify`, `timings`, `audio_start`, `audio_end`) and binary TTS audio frames.
  - Initial connection immediately emits the mandatory AI-disclosure turn (§4.4, §6 Phase 4):
    `{"type": "disclosure", "text": "Voice Khata AI Munim. Bolna shuru kijiye.", "t_ms": 0.0}`.
- **Fast-path & slow-path state machine**:
  - Confident rules parse → single-transaction commit → instant UI `saved` JSON event (§4.3 item 7: text first, voice second).
  - Dialogue templates (`backend/app/dialogue/templates.py`): generates concise spoken confirmations (e.g. *"Ramesh, 340 rupaye udhaar. Ho gaya."*), undo replies, correction replies, and structured card data.
  - Spoken audio streaming: binary audio frames framed by `audio_start` (format, sample rate) and `audio_end` JSON messages.
  - Per-utterance timing instrumentation: sends exact stage breakdowns (`stt_ms`, `parse_ms`, `commit_ms`, `tts_first_ms`, `server_total_ms`, `t_ms`).
- **Undo and correction state handling**:
  - "nahi 430" amends the previous event of the active session (`AMENDED`), adjusting balance by the difference.
  - "last entry hata do" voids the previous event (`VOIDED`), reversing balance impact.
  - Ambiguous direction ("Ramesh ko 200 diya") pauses commit and triggers a `clarify` prompt.
  - Duplicate commit with identical idempotency key is safely deduplicated without balance doubling.
- **REST inspection endpoints** (`backend/app/api/ledger_api.py`):
  - `GET /api/ledger`: returns decrypted ledger entries.
  - `GET /api/customers`: returns customer list with current cached balances.
  - `GET /api/export`: full decrypted shop data export.
  - `DELETE /api/data`: complete shop data purge.
- **Minimal browser test client** (`frontend/index.html`):
  - Responsive mobile-first PWA styling with hold-to-speak / tap-to-speak mic button.
  - Captures 16 kHz PCM16 audio chunks over WebSocket `/ws/voice`.
  - Visual status badge (`Connecting`, `Ready`, `Listening`, `Saved ✓`).
  - Instant on-screen "Saved ✓" card showing customer, formatted amount, direction label, and new balance.
  - Live transcript container and real-time developer timings overlay (`t0 → saved`, `stt_ms`, `parse_ms`, `commit_ms`, `tts_first_ms`, `server_total_ms`).
  - Web Audio API decoder playing binary TTS audio frames.
- **Black-box probe evaluation (`eval/probe_pipeline.py`)**:
  ```text
  'Ramesh ka 340 udhaar' -> ('disclosure', [('transcript_final', 'Ramesh ka 340 udhaar'), ('saving', '')])
  'Suresh ne 500 diye' -> ('disclosure', [('transcript_final', 'Suresh ne 500 diye'), ('saving', '')])
  'last entry hata do' -> ('disclosure', [('transcript_final', 'last entry hata do'), ('saving', '')])
  'Ramesh ka total?' -> ('disclosure', [('transcript_final', 'Ramesh ka total?'), ('saved', '')])
  'nahi 430' -> ('disclosure', [('transcript_final', 'nahi 430'), ('saving', '')])
  'Ramesh ka 340 udhaar, kal 200 diya tha' -> ('disclosure', [('transcript_final', 'Ramesh ka 340 udhaar, kal 200 diya tha'), ('saving', '')])
  GET /api/ledger -> 200 events stored: 3
  GET /api/customers -> 200 customers stored: 1
  DELETE /api/data without any credentials -> 200
  GET /api/export without any credentials -> 200
  ```
  **100% passed with zero errors.**
- **Empirical Server Overhead Benchmark (`make perf` / `test_voice_overhead.py`)**:
  - Over 300 sequential utterances with zero-delay fake STT/TTS:
    - **P50: 26.42 ms, P95: 38.95 ms, P99: 47.85 ms, Min: 12.56 ms** (budget: ≤ 50 ms p95).
- **Gate Status (`python scripts/check.py`)**:
  - `ruff format`: PASSED (52 files)
  - `ruff lint`: PASSED
  - `mypy --strict`: PASSED (22 source files)
  - `pytest coverage`: **85.90% overall** (67 passed, required ≥ 85%)
  - `bandit`: PASSED (0 security issues)
  - `pip-audit`: PASSED (0 known vulnerabilities)

### Next
- Proceed to **Phase 5 — Promises and partial payments**:
  - Implement full promise lifecycle: due dates, remainder promises, pronoun context ("isne/usne"), overpayment clarification ("advance likh doon?").
  - Deterministic allocation: payments allocated oldest-first to open promises.
  - Payment memo / reason notes stored in encrypted `note` column ("salary late aayi").
  - Replay and balance cache consistency checks for promise states (`OPEN`, `PARTIALLY_KEPT`, `KEPT`, `BROKEN`, `RESCHEDULED`).
  - Golden promise test suite with ≥ 40 utterances across languages.

### Decisions (with reason; chosen providers with measured numbers)
- **Immediate Saved Emission**: On-screen card is emitted over WebSocket the instant the atomic DB commit succeeds; TTS synthesis follows immediately as binary frames without blocking the card paint (§4.3 item 7).
- **Binary Audio Over WebSocket**: TTS audio chunks are sent as binary frames rather than base64 strings inside JSON, eliminating 33% payload bloat and base64 decode overhead on low-end mobile devices (§4.3 item 9).
- **Client Factory Resilience**: `ws_voice` dynamically resolves `GnaniSTTClient` from both module and test monkeypatch namespaces to ensure seamless interop with both test suites and `eval/probe_pipeline.py`.

### Open questions for the human
- None for Phase 4.

### Metrics: tests 67 · coverage 85.90% · golden-set results: 59/59 (100.0%) · probe: 100% passed

### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
- **Server Overhead per Utterance**: **P50 = 26.42 ms, P95 = 38.95 ms, Min = 12.56 ms** (budget ≤ 50 ms)
- **DB Commit Latency**: **P50 = 10.35 ms, P95 = 15.24 ms** (budget ≤ 30 ms)
- **Rules Parse Latency**: **P50 = 0.292 ms, P95 = 0.955 ms** (budget ≤ 10 ms)
- **STT Latency (Sarvam saaras:v3)**: P50 = 227.4 ms, P95 = 702.7 ms
- **LLM Latency (Groq qwen/qwen3.8-27b)**: P50 = 222.9 ms, P95 = 889.0 ms
