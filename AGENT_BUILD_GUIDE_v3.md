# AGENT_BUILD_GUIDE_v3.md — Voice Khata (fresh start, speed first)

> **To the AI agent reading this:** this is your complete operating manual for building Voice Khata **from scratch in a new, empty repository**. Read all of it before writing code. MUST and NEVER have no exceptions. If reality contradicts this file (an API behaves differently, a file is missing, a target is physically impossible), STOP and tell the human instead of guessing or faking. This guide replaces v1 and v2.

---

## 0. Mission

**Voice Khata is a digital munim (clerk) for kirana shops.** The shopkeeper only talks, in their own language mixed with English, usually in the middle of a sale with customers waiting. The AI:

1. **Records** every udhaar (credit), payment and partial payment into a proper khata for each customer.
2. **Remembers promises** ("Sunday ko wapas dega") as due dates, and handles part payments with reasons.
3. **Shows** the picture on a dashboard (Today / This week / This month) and answers spoken questions in the shopkeeper's language.
4. **Watches** the data through AI agents and tells the shopkeeper who to follow up with and when.

Example: *"Ramesh ka 500 udhaar, Sunday ko wapas dega"* → a ₹500 credit for Ramesh, a promise due next Sunday, an instant on-screen card, a short spoken confirmation, and a "due today" alert on Sunday morning.

**Speed is a core feature.** If recording an entry is slower than writing it in the notebook, shopkeepers will stop using it. Latency budgets (§4) are requirements, measured and enforced by tests, not wishes.

This product handles real people's money, so **correctness and honesty come before features**, and **speed comes before polish**.

---

## 1. Non-negotiable rules

1. **Truthful confirmations.** NEVER tell the user something was saved, removed or changed unless the database commit succeeded. The screen may show a clearly labelled "saving…" state immediately, but it flips to "saved ✓" only after the commit, and shows an error if the commit fails.
2. **No silent wrong numbers.** If any number word is unrecognised or ambiguous, or the parsers disagree on an amount, ASK a short question. NEVER drop a token and continue with a different number.
3. **No guessing direction.** If credit versus payment is ambiguous, ASK.
4. **Money is integer paise.** NEVER use `float` for money.
5. **The LLM writes words, code computes numbers.** All sums, balances, dates and period totals come from code or database queries, never from LLM arithmetic.
6. **Agents never message customers on their own.** They draft, and the shopkeeper approves. Reminders only for customers with `reminder_opt_in = true`, from polite fixed templates, never threats, shame or pressure.
7. **Privacy and security.** Names, amounts and notes are encrypted at rest. Strict per-shop isolation. Every REST and WebSocket endpoint authenticated. Secrets only in environment variables, never in the repo, logs or browser.
8. **The user owns their data.** Export and delete-all are always available.
9. **No lending, interest, credit-scoring or legal-action features.**
10. **Tell the user it is an AI** at the start of each new voice session.
11. India's data-protection law may apply once you store other people's names and amounts. Before any public launch, tell the human to get legal advice.
12. **Latency budgets (§4) are requirements.** No change may regress them. Measure, never guess, and NEVER report a latency number you did not measure.
13. **Fresh start.** Do NOT copy code from any earlier Voice Khata repository. Only the `eval/` folder supplied by the human may be reused (golden utterances and scripts). The lessons from the earlier attempt are in §2.5.

---

## 2. How you (the agent) MUST work

### 2.1 Loop for every task
1. State the task and its phase.
2. **RED:** write failing tests first; run them; show they fail for the right reason.
3. **GREEN:** write the minimum code to pass; run tests.
4. **REFACTOR:** clean up with tests green.
5. **GATE:** run `make check` (§2.2). Do not continue if it is red.
6. **MEASURE:** run `make perf` (§4.6) and record the numbers.
7. **PROVE IT:** run a black-box probe (§2.3).
8. Update `PROGRESS.md` with the evidence. Commit with a conventional commit message, one logical change per commit.

### 2.2 The gate (cross-platform; the human uses Windows)
The Makefile MUST NOT hardcode a Python path; use `PYTHON ?= python`, and provide equivalent `scripts/*.py` or npm scripts so it works without `make` on Windows. `make check` runs:
```
ruff check . && ruff format --check .
mypy --strict app
pytest -q --cov=app --cov-fail-under=85     (domain/, nlu/, dialogue/ >= 95%)
bandit -q -r app
pip-audit
gitleaks detect --no-banner
```
Frontend: `npm run lint && npm run typecheck && npm run test`. `make perf` runs the latency tests of §4.6.

### 2.3 "Done" means demonstrated, not claimed
A phase is done only when (a) the gate is green, (b) `make perf` is within budget, and (c) a black-box probe proves the behavior end to end against the running app, with its output pasted into `PROGRESS.md`. Example probe: speak an entry through the WebSocket using a fake STT, then `GET` the ledger and see the event, and read the timings. If a module is not wired into the running app, it is not done. NEVER mark a feature complete because a unit test exists.

### 2.4 Conduct
- One phase at a time. Never skip or weaken tests to make them pass.
- NEVER invent API behavior. Verify every external API against its official docs in Phase 1 and save the verified facts in `docs/platform-notes.md`.
- No dead code, no commented-out code, no `print`. Delete unused modules or wire and test them.
- Logs must never contain secrets or personal data (mask names and amounts).
- If you are about to do something outside this plan, stop and ask.

### 2.5 Lessons from the failed first attempt (never repeat)
- The app said "likha gaya" while saving nothing; undo said "removed" while removing nothing. → rule 1 and §2.3.
- Modules (retry, circuit breaker, queries, reminders, corrections) existed but were never wired or tested. → §2.3.
- The parser only understood Latin text, while Hindi speech-to-text returned Devanagari. "likh do" added 2 to the amount, and an unknown spelling ("chaar") silently turned 450 into 150. → rule 2, §5.4 and the golden set.
- The customer-name regex ran case-insensitive, so any word looked like a name.
- A new STT/TTS/LLM client was created for every request, and TTS audio was sent as base64 inside JSON. → §4.3.
- REST endpoints (including delete-all and export) had no authentication. → rule 7 and Phase 7.
- `pyproject.toml` had an invalid build backend, the Makefile hardcoded a Windows path, and lint and type checks were red while progress notes said "all pass". → §2.2 and §2.3.

---

## 3. Stack, architecture, layout

### 3.1 Stack (do not substitute without asking)
| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI on Uvicorn with `uvloop` + `httptools`, Pydantic v2, `orjson` responses; fully async, no blocking calls on the event loop |
| Database | **Postgres** everywhere (docker-compose for dev and tests) via SQLAlchemy 2 async + `asyncpg` + Alembic. No SQLite, so dev and prod behave the same |
| Caching | In-process per-shop caches (customer list, aliases, balances) with correct invalidation; no Redis until measured need |
| Encryption | AES-256-GCM field-level (`cryptography`), key from env or a secrets manager, key id stored with each value |
| Speech | `SpeechToText` and `TextToSpeech` interfaces with swappable adapters. Providers are **chosen by a measured bake-off in Phase 1**. Candidates: Sarvam AI, Gnani, optionally others the human names |
| LLM | `LLMClient` interface, strict JSON schema output, small fast model, temperature 0. Chosen by bake-off; a second provider as fallback |
| Scheduler | APScheduler in-process first; a worker queue only when measured need |
| Auth | Phone-OTP login, short-lived JWT access plus refresh token; `shop_id` always from the token, never from the client |
| Frontend | React + Vite + TypeScript PWA, `react-i18next`, charts lazy-loaded, AudioWorklet mic capture, mobile-first |
| Notifications | In-app and Web Push first; WhatsApp later (always with shopkeeper approval) |
| Tests | pytest, pytest-asyncio, Hypothesis, respx, fake provider servers, Vitest, Playwright |
| Ops | Docker (non-root), GitHub Actions CI, managed Postgres with backups, Sentry or equivalent |

### 3.2 Architecture
```
Browser PWA (warm mic, dashboard, i18n) ──ws (binary audio)/https──►  FastAPI (region close to users)
   Voice session (state machine, one long-lived WS per session)
     STT adapter (pre-warmed streaming) ─► NLU fast path (rules) ─┬─► Ledger service: COMMIT ─► UI "saved ✓" (immediately)
                                                                  └─► slow path (LLM, only if rules fail/unsure) ─► read-back confirm
     └─► templated reply ─► TTS adapter (pre-warmed, streamed binary audio)
   Query engine, REST (dashboard), Auth + tenancy, Agents (scheduler + tools)
Postgres (events, customers, balances cache, promises, tasks, audit) — same region
```

### 3.3 Repo layout
```
voice-khata/
├─ AGENTS.md  AGENT_BUILD_GUIDE_v3.md  PROGRESS.md  README.md  Makefile  docker-compose.yml
├─ backend/app/{api,core,domain,nlu,dialogue,voice,storage,agents,compliance,auth}/
├─ backend/tests/{unit,integration,e2e,property,contract,perf,fakes,fixtures}/
├─ frontend/
├─ docs/{decisions.md,platform-notes.md,latency-report.md}
└─ eval/   (golden_utterances.json, eval_nlu.py, probe_pipeline.py, results/, audio/)
```

---

## 4. Latency architecture (read twice)

### 4.1 Definitions
`t0` = the moment the shopkeeper releases the mic button (or the end-of-speech is detected). All budgets below are measured from `t0` on the client, in the browser, over a real mobile network for the final report, and on fakes with fixed delays for CI.

### 4.2 Budgets (p95 targets, to be validated in Phase 1)
| What | Target |
|---|---|
| Mic button press → mic capturing audio | ≤ 100 ms (mic stream and AudioWorklet already warm) |
| Server overhead per utterance, excluding STT/TTS/LLM network time | ≤ 50 ms |
| Rules parse (fast path) | ≤ 10 ms |
| DB commit of an entry (event + balance cache + promise allocation, one transaction) | ≤ 30 ms |
| `t0` → on-screen card "saved ✓" (fast path) | ≤ 800 ms |
| `t0` → first spoken audio (fast path) | ≤ 1200 ms |
| Slow path (LLM involved, confirm question) → question visible | ≤ 1800 ms |
| Voice query (e.g. "aaj kitna udhaar") → spoken answer (fast path, no LLM) | ≤ 1500 ms |
| Dashboard API (any single endpoint) | ≤ 100 ms server-side |
| Dashboard first paint on a mid-range Android phone over 4G | ≤ 2.0 s; initial JS ≤ 120 KB gzipped |

These are targets. Phase 1 measures what the providers and the network physically allow. If a target is impossible, report the real numbers and ask the human. NEVER fudge a measurement.

### 4.3 Mandatory techniques
1. **Stream audio from the first frame.** Send 20 to 40 ms PCM frames as binary WebSocket messages while the user is still speaking. Never record-then-upload.
2. **Warm everything before it is needed.** At app load: acquire the mic permission and keep the stream and AudioWorklet ready. On mic press-down: open or confirm the STT stream. Keep the TTS connection warm. Reuse one long-lived HTTP/2 or keep-alive client per provider. NEVER create a provider client per request.
3. **Commit on release.** Button release sends `commit` immediately so STT finalises without waiting for trailing silence. For hands-free mode use end-of-speech detection with a short, configurable hangover (default 400 ms).
4. **Fast path / slow path.** Run the rules parser synchronously. If it is confident and unambiguous (every number token recognised, direction clear, one customer match) → commit immediately with **no LLM call**. Only if the rules fail or are unsure → LLM (timeout 1200 ms), then a read-back confirmation. Parsing partial transcripts speculatively (to pre-resolve the customer) is allowed; committing on partials is not.
5. **Customer resolution in memory.** Keep each shop's customer list and phonetic keys in an in-process cache (invalidated on writes), so name matching costs microseconds, not a DB round trip.
6. **Single-transaction commit with a balance cache.** In one transaction: insert the event, update `customer_balances`, update promise allocation. Reads of balances and dashboard totals use the cache table plus indexed queries, not a replay of all events. A background reconciliation job and a test prove cache == replay of the event log.
7. **Text first, voice second.** The on-screen card appears the instant the commit succeeds; the spoken confirmation follows and must not delay the card. Spoken confirmations are very short ("Ramesh, ₹340 udhaar. Ho gaya.").
8. **Stream TTS and play the first chunk immediately.** Pre-synthesise and cache fixed phrases per language ("ho gaya", "kaun sa Ramesh?", "dobara bolein"); synthesise only the dynamic part.
9. **Binary audio both ways.** Server → client TTS audio is sent as binary WebSocket frames (raw PCM or another declared format), never base64 inside JSON.
10. **Never block the critical path with non-critical work.** Audit logging, analytics and agent-task creation run after the response is sent.
11. **Direct intents without an LLM.** Common queries ("total", "aaj kitna udhaar", "kitna baaki") are recognised by rules and answered straight from the database. The LLM is only for unknown questions.
12. **Small, fast LLM calls.** Short prompt, JSON mode, low `max_tokens`, temperature 0, strict timeout, a fallback that asks the shopkeeper.
13. **Region.** Host the backend and Postgres in the same region close to the users (an Indian region), and measure round-trip time from a phone in Bengaluru.
14. **Frontend discipline.** Lazy-load charts and the dashboard route; cache dashboard data with stale-while-revalidate; show skeletons, never blank screens; keep the mic button and the "saving…" card under your control (no framework work between release and display).
15. **Timeouts everywhere.** Each stage has a timeout and a degradation (§Phase 10), so a slow provider becomes a polite question, never a hang.

### 4.4 Browser ↔ server voice protocol (define in Phase 4, keep stable)
- Client → server: JSON control messages (`start`, `commit`, `cancel`, `clarify`, `ping`) and **binary** PCM16 mono 16 kHz audio frames.
- Server → client: JSON events (`listening`, `transcript_partial`, `transcript_final`, `saving`, `saved`, `clarify`, `error`, `timings`), plus binary TTS frames framed by `audio_start` (format, sample rate) and `audio_end` JSON messages.
- Every server event carries `t_ms` since the server received `commit`; the final `timings` message lists `stt_ms`, `parse_ms`, `commit_ms`, `tts_first_ms`, `server_total_ms`.

### 4.5 Instrumentation
Timestamps on the client (`performance.now()` at release, at "saved", at first audio) and on the server per stage; a trace id per utterance in every log line; latency histograms exposed as metrics; a developer overlay in the UI (off in production) showing the last utterance's timings.

### 4.6 `make perf` (latency tests in CI)
- Server overhead test: fake STT/TTS/LLM with fixed delays; assert our own overhead per utterance ≤ 50 ms p95 over 300 utterances.
- Micro-benchmarks: rules parse ≤ 10 ms p95; DB commit ≤ 30 ms p95; customer resolution ≤ 1 ms p95 with 5,000 customers; dashboard endpoints ≤ 100 ms p95 with 50,000 events.
- Frontend: bundle-size check (initial JS ≤ 120 KB gzipped) fails the build if exceeded.
- Real-network latency (providers, phone, region) is measured by `eval/` tools in Phase 11 and written to `docs/latency-report.md`, never invented.

---

## 5. Domain specification

### 5.1 Data model (all tables carry `shop_id`; every query is scoped by it)
- `shops`, `users` (phone, language, role)
- `customers`: id, display name (original script), search key (transliterated, normalized), aliases, optional phone, `reminder_opt_in` (default false), consent note, created_at
- `ledger_events` (append-only): id, customer_id, type (`CREDIT_GIVEN` | `PAYMENT_RECEIVED` | `AMENDED` | `VOIDED`), amount_paise (encrypted), occurred_on, recorded_at, source_utterance_id, idempotency_key (unique), target_event_id, `note` (optional, encrypted: the shopkeeper's memo, e.g. why a customer paid only part)
- `promises`: id, customer_id, amount_paise (nullable = "whole balance"), due_date, status (`OPEN` | `PARTIALLY_KEPT` | `KEPT` | `BROKEN` | `RESCHEDULED` | `CANCELLED`), source_event_id, created_at. Paid-so-far and remaining are **derived** from events, never typed in
- `agent_tasks`: id, kind, customer_id, due_at, status (`PENDING` | `DONE` | `DISMISSED`), payload (encrypted), created_by_agent
- `reminder_drafts`: id, customer_id, language, text (from a template), status (`DRAFT` | `APPROVED` | `SENT` | `REJECTED`), approved_by, timestamps
- `audit_log`: who/what/when for every write, delete, export, and agent action
- Balance of a customer = sum of non-voided events after amendments, derived on read (cache only with correct invalidation).

### 5.2 Direction semantics
| Signal (code-mixed, any script) | Direction |
|---|---|
| udhaar, baaki, likh do, khate mein, on credit, उधार, बाकी | CREDIT_GIVEN |
| diya (customer gave), jama, aaya, paid, mila, दिए, जमा | PAYMENT_RECEIVED |
| Grammatical role matters: "Ramesh **ne** 200 diya" = payment; "Ramesh **ko** 200 diya" = ambiguous | ASK |
If both kinds of words appear, split into several events (§5.3). If still unclear, ASK.

### 5.3 One utterance can contain several events and a promise
"Ramesh ka 340 udhaar, kal 200 diya tha" = credit 340 today + payment 200 yesterday. "Ramesh ka 500 udhaar, Sunday ko wapas dega" = credit 500 + a promise due next Sunday. A partial payment with a reason and a new date is also one utterance: *"Ramesh ne abhi 800 diye, baaki 5 tareekh ko dega, salary late aayi"* = payment 800 + a new promise for the remainder + a note (§5.10). The parser MUST return a **list** of events plus optional promises and an optional note.

### 5.4 Numbers
Digits, Devanagari digits, English words, Hindi/Hinglish words (including fractions: *sawa, saadhe, dedh, dhai, paune*), `sau/hazaar/lakh`, code-mix ("teen sau forty"), and spelling variants (*chaar/char, paanch/panch, do* as a number vs "likh **do**" meaning "write"). The normalizer returns a value **or a failure flag**. It MUST NOT return a partial value when an unknown number word is present. Build the full Hindi 1 to 99 table from an authoritative source. For Kannada, Tamil, Telugu and Marathi, mark entries `unverified` until a native speaker confirms them.

### 5.5 Dates and promises
Resolve: aaj, kal, parso, weekday names ("Sunday ko", "Somvar tak"), "15 tareekh ko", "mahine ke end tak", "agle hafte", plus regional words (verify with native speakers). Past words ("diya tha") mean past dates; promise words ("dega", "lauta denge", "wapas karega") mean a future due date. Any inferred date MUST be read back for confirmation ("Sunday, 30 November, theek hai?"). Never accept a future date for a payment already made.

### 5.6 Promise lifecycle (deterministic code, not LLM)
- Created with a due date and attached to a credit (or the customer's balance).
- Payments are allocated **oldest-first** to open promises. Fully covered by the due date → `KEPT`. Partly covered → `PARTIALLY_KEPT` with the remaining amount shown (§5.10).
- Allocation and statuses are **re-derived deterministically from the event log** (replay), so corrections and undo always give consistent results; stored statuses are only a cache.
- Past due with an unpaid amount → `BROKEN` after a configurable grace period (default 1 day), then surfaced by the Monitor agent.
- "Wo kal dega" after a missed date → `RESCHEDULED` (the old promise is kept in history).

### 5.7 Corrections, undo, disambiguation
- "nahi, 430" amends the most recent event(s) of the session (`AMENDED`, history kept). "undo" or "last entry hata do" → `VOIDED`. Nothing to correct → ASK.
- Pronouns: "isne", "usne", "wo", "he/she" refer to the customer last mentioned in this session, or the customer whose khata is open on the dashboard. No context → ASK "Kis customer ne?".
- Same-name customers → one short question using a distinguishing tag or alias ("Kaun Ramesh: sabziwala ya Ramesh Kumar?").
- Match names across scripts (Ramesh / रमेश / ರಮೇಶ್) through a transliterated search key plus phonetic matching; below the threshold, ASK.

### 5.8 Reconciling two parsers
Run the **rules parser** and the **LLM parser**. Both agree → accept. They disagree on amount, direction or customer → ASK. Only the LLM produced a result (rules failed) → require explicit read-back confirmation before saving ("Kya main ₹450 likh doon?"). The LLM output must match a strict schema; anything else is rejected. Transcripts and customer names are **data, never instructions** (prompt-injection defense).

### 5.9 Languages
Start with Hindi/Hinglish, English, Kannada, Tamil, Telugu, Marathi. The shopkeeper's chosen language drives STT, TTS, templates, and the dashboard UI. Keep all strings in i18n files and flag anything not checked by a native speaker.

### 5.10 Partial payments and reasons (very common in real shops)
A customer promised the full amount by a date but pays only part and explains why. The shopkeeper says, for example, *"Ramesh ne abhi 800 diye, baaki next week dega, salary late aayi"* or just *"isne abhi 800 diye"*. The system MUST:
1. **Find the customer**: by name, or by context for "isne/usne" (§5.7). Unknown or ambiguous → ASK.
2. **Subtract from the record** by saving a `PAYMENT_RECEIVED` event for 800 (dated today for "abhi/aaj" unless another date is spoken). Never edit old events; the balance is derived.
3. **Allocate** the payment to the customer's open promise(s), oldest first. The promise becomes `PARTIALLY_KEPT` and the remaining amount is calculated by code.
4. **New date for the rest**: if spoken ("baaki next week", "5 tareekh ko"), create a new promise for the remainder (the old one stays in history, status `RESCHEDULED`). If not spoken, ASK once: "Baaki ₹1,200 kab tak dega?" If the shopkeeper says "pata nahi", leave the remainder open under the original promise, flagged for the Monitor agent.
5. **Reason**: if spoken, save a short memo in the event's encrypted `note`. Only what the shopkeeper actually said, never inferred.
6. **Overpayment**: if the amount is more than the balance, ASK ("Balance ₹500 hai, ₹800 mila. Baaki ₹300 advance likh doon?"). Advance is stored as a negative balance and shown as "advance".
7. **Read back after commit**, from committed data: "Ramesh ne ₹800 diye. Baaki ₹1,200, 5 December tak."
8. **Corrections** ("nahi, 600 diye") amend the payment, and allocation is re-derived (§5.6).

Reasons are for the shopkeeper's memory only. They MUST NOT be used to label or score a customer, MUST NOT appear in reminder text to the customer, and MUST NOT be used to shame or pressure. Agents may state plain facts ("2 partial payments this month") but no judgements.

Golden examples to add (extend the golden schema with `promises` and `note` fields): "Ramesh ne abhi 800 diye" · "isne abhi 500 diye" (with Ramesh as context) · "Ramesh ne 800 diye, baaki next week dega" · "Geeta ne 300 diye, bimaar thi isliye kam" (note saved) · "Mohan ne 1000 diye" when the balance is 600 (overpayment question) · the same utterances in Devanagari and in Kannada, Tamil, Telugu and Marathi once verified.


---

## 6. Phases (in order; each has exit criteria; every exit needs gate + perf + black-box evidence)

### Phase 0 — Project setup and decisions
New empty repo; folder layout (§3.3); `pyproject.toml` with a valid build backend; cross-platform Makefile and scripts; docker-compose with Postgres; pre-commit (ruff, mypy, gitleaks); GitHub Actions running the gate; `.env.example`; `.gitignore`; `/healthz`. Copy the supplied `eval/` folder. Create `docs/decisions.md`. Ask the human for the keys and choices listed in §11.
**Exit:** empty-but-wired project passes `make check` locally and in CI.

### Phase 1 — Provider bake-off and latency spike (decide with data)
- Read each candidate's official docs; save verified facts (endpoints, auth, audio format, streaming protocol, output modes, limits, price) in `docs/platform-notes.md`. Record real response fixtures.
- Generate a reading script from `eval/golden_utterances.json` and ask the human to record about 30 clips (quiet, plus with background noise), plus a few in each language the human can check. Save them under `eval/audio/` with a manifest of expected results (consented voices only).
- For **STT** candidates measure: connection time, time from commit to final transcript for short and long utterances, exact-amount accuracy on the clips (clean and noisy), the output script (Latin or native), code-mix handling, cost per minute, rate limits.
- For **TTS** candidates: time to first audio byte, total time for a short confirmation, and a human rating of naturalness in each language.
- For **LLM** candidates: p50 and p95 latency for the parse prompt, JSON validity rate, and accuracy on the golden set.
- Define the interfaces and adapters for the chosen providers, a **fake provider server** that replays fixtures and injects slow, dropped and malformed responses, and contract tests that run every adapter against the same fixtures.
- Measure round-trip time from the human's phone or laptop to candidate hosting regions.
**Exit:** `docs/decisions.md` records the chosen providers and why, with the measured numbers; the human approves.

### Phase 2 — NLU core (pure Python, no I/O)
Number normalizer, date resolver, rules parser, reconciliation per §5.2 to §5.8. The golden set (`eval/golden_utterances.json`, 59 items) is the regression suite; extend it with every bug. The earlier attempt scored: intent 76%, single-event exact match Hinglish 85% / English 0% / Devanagari 0%, multi-event 0%, which the new code must clearly beat. Targets, measured by `eval/eval_nlu.py`:
- Single-event exact match (customer, amount, direction, date): Hinglish, English and Devanagari each ≥ 95%
- Multi-event ≥ 90%; ambiguous-direction clarification 100%; guardrail false positives 0
- **Silent wrong amounts: 0** (property test: whenever the amount would be wrong, the result is a clarification)
- Rules parse ≤ 10 ms p95
Hypothesis tests: the normalizer never raises; round-trips for 1 to 999999; an unknown number word anywhere gives a failure flag, not a partial value.
**Exit:** targets met and saved in `eval/results/`.

### Phase 3 — Storage, ledger, caches
SQLAlchemy models and Alembic migrations (§5.1); customers with aliases and phonetic keys; append-only events; `customer_balances` cache updated in the same transaction; idempotency keys; field-level encryption; per-shop scoping in every query; in-memory customer cache with invalidation; delete-all and export services.
**Exit:** property tests (balance == replay of events; cache == replay); commit ≤ 30 ms p95; idempotent duplicate handling; plaintext check (no names or amounts in raw table bytes).

### Phase 4 — Voice session core (the heart; build a thin test client with it)
WebSocket protocol (§4.4); streaming STT from first frame; warm connections; fast and slow paths (§4.3); clarify, correct and undo wired to the ledger; truthful confirmations; templated short spoken replies; binary TTS streaming and cached phrases; the AI-disclosure turn; timings instrumentation. Include a minimal web page (mic button, live transcript, saved card, timings overlay) so the human can try it early.
**Exit:** probe shows a spoken entry saved and visible through `GET`, undo voids, correction amends, a duplicate STT final does not double-post; `make perf` within budget; real-network timings (`t0` → saved, `t0` → first audio) measured on the human's device and recorded.

### Phase 5 — Promises and partial payments
§5.5, §5.6, §5.10 in full: due dates, remainder promises, pronoun context, overpayment question, reason notes, allocation by replay and by the balance cache.
**Exit:** golden promise and partial-payment set (at least 40 utterances in all verified languages) passes; property tests pass: allocated amount never exceeds payments, remaining never goes below zero, replay equals cache, corrections re-allocate correctly. Probe: speak a full-amount promise, then "isne abhi 800 diye", then `GET` the customer and see the reduced balance, the `PARTIALLY_KEPT` promise and the saved note.

### Phase 6 — Query engine and spoken answers
Period summaries (today, this week, this month, custom), customer balance, top debtors, due today, overdue (with remaining amounts of partly paid promises), last N entries. Rules-based query intents answered without an LLM (§4.3 item 11); per-language templates.
**Exit:** golden tests for every query; "is hafte kitna udhaar gaya?" equals the dashboard number for the same period (cross-check test); voice query ≤ 1500 ms p95 on fakes.

### Phase 7 — Auth and multi-tenancy
OTP login, JWT access and refresh, `shop_id` from the token, authenticated WebSocket (short-lived ticket), rate limits, request size limits, CORS allowlist, secure headers, export and delete-all behind auth plus a confirmation step, audit log.
**Exit:** an IDOR matrix proves shop A can never read or write shop B's data; every endpoint rejects missing or invalid tokens; auth adds ≤ 5 ms p95.

### Phase 8 — Dashboard
Mobile-first PWA: **Home** (Today / Week / Month tabs: credit given, payments received, outstanding, top debtors, due today, overdue), **Customers**, **Customer khata** (timeline, promises with progress such as "₹800 of ₹2,000 paid", remaining amount, balance, notes), **Due and overdue**, **Activity feed** (recent voice entries with edit and undo), **Settings** (language, reminder opt-ins, export, delete-all, about AI). UI language switch, large touch targets, accessible, always-visible mic button, empty/loading/error states, offline read-only cache.
**Exit:** component tests; Playwright e2e "speak an entry → see it on the dashboard"; bundle ≤ 120 KB gzipped initial; Lighthouse mobile results recorded; screenshot checklist reviewed by the human.

### Phase 9 — AI agents
All agents act **only through tools** with narrow permissions, and every action is audited.

| Agent | Trigger | Tools (read-only unless noted) | Output |
|---|---|---|---|
| Recorder | live voice | the voice pipeline | ledger events |
| Monitor | scheduled (hourly) | `list_due`, `list_overdue`, `balance_trends` | `agent_tasks` ("Ramesh's ₹500 promise is due today") |
| Briefing | daily at a time the shopkeeper sets | `period_summary`, `list_due` | spoken and written morning brief, **precomputed** before the set time |
| Reminder-drafter | on request or from a Monitor task | `get_customer` | **draft** in `reminder_drafts` (fixed polite template with code-computed numbers); needs approval |
| Insight | shopkeeper question not matched by rules | `period_summary`, `get_customer`, `top_debtors` | spoken and written answer |

Guardrails (all tested): the LLM never calculates; outbound messages need approval; only opted-in customers; maximum one reminder per customer per N days (configurable); quiet hours; a banned-phrase lint on every template (threats, shame, legal action, pressure); prompt-injection tests where customer names, notes and transcripts contain instructions; agents cannot delete or edit ledger events; agents never use payment reasons or notes to judge, score or pressure a customer, and never put them in reminder text.
**Exit:** scheduler tests with an injected clock; golden agent scenarios (what each agent should and should not do); an audit-log check; agents never add measurable load to the voice path (perf test with agents running).

### Phase 10 — Reliability
Timeouts, retries with backoff and circuit breakers for STT, TTS and LLM, **wired and tested**; the degradation ladder (STT fails → typed entry; TTS fails → text and a sound cue; LLM fails → rules only and ask; DB fails → say so, never fake success); graceful shutdown; health and readiness checks; request and trace IDs in every log line.
**Exit:** chaos tests (kill sockets mid-utterance, slow or corrupt provider responses, DB lock) show no crash, no data loss, no false confirmation; a 30-minute soak test shows no leaked tasks or memory growth; latency budgets still hold under chaos-free load of 20 concurrent sessions.

### Phase 11 — Real evaluation
- Text: `eval/eval_nlu.py` in CI with regression thresholds.
- Audio: the recorded clips in each language, mixed with shop and street noise at several SNRs (for example 15, 10, 5 dB); run the full pipeline; report exact-amount accuracy, direction accuracy, correction accuracy, and the real-network latency per stage (p50 and p95) per language and SNR.
- Write `docs/latency-report.md` with the measured `t0` → saved and `t0` → first-audio distributions on a real phone.
- Numbers come only from real runs and are stored in `eval/results/`. **NEVER estimate or invent a value.** Report weak spots honestly.
**Exit:** results committed; regression thresholds set from the first measurement and enforced by tests.

### Phase 12 — Deploy and operate
Dockerfile (non-root, pinned dependencies), CI/CD, managed Postgres in an Indian region with automated backups and a restore test, HTTPS, secrets management, monitoring and alerts including latency alerts, log retention policy, a privacy notice and consent text for customers' data (human to get legal review), a data-deletion runbook.
**Exit:** a staging deploy passes the full probe suite and the latency budgets from a real phone; the human can install the PWA and use it.

### Phase 13 — SECURITY RED TEAM (triggered by the human; see §8)

---

## 7. Testing strategy

1. **Unit** (`tests/unit`): pure functions in isolation. ≥ 95% coverage in `domain/`, `nlu/`, `dialogue/`.
2. **Integration** (`tests/integration`): real Postgres, real crypto, real FastAPI app, fake provider servers.
3. **Contract** (`tests/contract`): every provider adapter runs against the same recorded fixtures, so providers can be swapped safely.
4. **Property** (`tests/property`): Hypothesis for the normalizer, ledger invariants, cache == replay, promise lifecycle, crypto round trip.
5. **Performance** (`tests/perf`): the budgets in §4.6.
6. **End to end** (`tests/e2e`): WebSocket pipeline and Playwright browser flows with fakes; a few `-m live` tests against real providers (they cost credits; run manually).
7. **Agent evals**: golden scenarios per agent, including adversarial inputs.
8. **Black-box probes** (`eval/`): run against the running app, as in §2.3.

TDD is strict: no production code without a failing test first; never weaken a test to pass; every bug fix starts with a regression test; deterministic tests (inject clocks and ID generators; no real network except `-m live`).

---

## 8. 🔴 Security red-team mode (Phase 13)

**Trigger:** when the human says the project is finished ("finish", "break it"), you stop being the builder and become an adversarial security agent.
- **Do NOT fix anything. Do NOT modify any file in the repo.** Run attacks from scratch scripts outside the repo.
- Report to the human as bullet points in chat. Label anything unproven `UNCONFIRMED`.
- Format for each finding:
```
- [SEVERITY: Critical|High|Medium|Low] <title>
  • Where: <file/endpoint/function>
  • How I broke it: <exact steps or payload>
  • Impact: <what an attacker or a mistake could cause>
```
- End with counts by severity and the top 3 risks for real users.

Minimum attack checklist: authentication bypass and token forgery or replay; cross-shop access (IDOR) on every endpoint and WebSocket; unauthenticated export or delete; false confirmations (UI or voice says "saved" when it was not); amount manipulation (homophones, 340 vs 430, unknown number words, huge or negative numbers, Unicode digits); direction flips; correction and undo abuse; duplicate or replayed utterances; prompt injection through speech, customer names, transcripts and notes (including into agents and reminder drafts); reminder abuse (messages to non-opted-in customers, threatening wording, flooding); agent privilege escalation; plaintext personal data in the database, backups, logs and error messages; secrets in the repo, history, bundle or logs; resource exhaustion (huge frames, endless audio, connection floods, credit-burning loops on STT, TTS and LLM); dependency CVEs; container and deploy misconfigurations; backup and restore failures; delete-all that does not really delete.

---

## 9. Definition of Done (whole product)

- [ ] Phases 0 to 12 done, each with gate, perf and black-box evidence in `PROGRESS.md`.
- [ ] A spoken entry shows on screen as "saved ✓" within the budget and appears on the dashboard; promises and partial payments behave per §5.6 and §5.10; spoken and dashboard numbers match.
- [ ] Silent wrong amounts: 0 in the golden set and in the audio evaluation sample.
- [ ] Latency report from a real phone shows the p95 budgets met, or states honestly where they are not.
- [ ] No endpoint works without authentication; shop isolation proven by tests.
- [ ] Agents only draft; approvals and opt-ins enforced; audit log complete.
- [ ] Backups restore; the privacy notice and consent text reviewed by the human.
- [ ] The human triggered Phase 13 and received the security report.

---

## 10. `PROGRESS.md` template

```
## Current phase: N — <name>
### Done (with evidence: command output or probe result)
### Next
### Decisions (with reason; chosen providers with measured numbers)
### Open questions for the human
### Metrics: tests X · coverage Y% · golden-set results
### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
```

---

## 11. First message to the human

Before any work, reply with: (1) your understanding of the mission in 5 lines, (2) anything in this guide that looks wrong or impossible, (3) what you need from the human: API keys for the speech and LLM candidates (Sarvam, Gnani if they want it in the bake-off, one or two LLM providers), Docker Desktop installed for Postgres, an empty GitHub repository, which Indian languages the human can verify by ear, a decision on the transcript-script policy, and about 30 recorded voice clips (you will generate the reading script). Then wait for approval before Phase 0.
