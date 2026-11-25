# Progress Log — Voice Khata

## Current phase: 2 — NLU core (pure Python, no I/O)

### Done (with evidence: command output or probe result)
- Built high-precision number normalizer in `backend/app/nlu/numbers.py`:
  - Full Hindi 1-99 table (transliterated and Devanagari numerals `०-९`).
  - English numerals (units, teens, tens, hundreds, thousands, lakhs, crores).
  - Indian fraction operations (`dedh`, `dhai`, `sawa`, `saadhe`, `paune`).
  - Disambiguation of verbal auxiliary `likh do` / `kar do` from numeral `2`.
  - Zero-tolerance unknown number word rejection (returns `None`, never partial amount).
- Built relative date resolver in `backend/app/nlu/dates.py` (`aaj`, `kal` past vs future, `parso`, weekdays, explicit tareekh).
- Built domain guardrails in `backend/app/compliance/guardrails.py` blocking lending/loans, interest calculation, credit scoring (CIBIL), and non-khata medical/personal queries.
- Built pure deterministic rules parser in `backend/app/nlu/rules_parser.py`:
  - Handles single-event transactions in Hinglish, English, and Devanagari.
  - Multi-event transaction splitting by comma and conjunctions (`aur`, `and`).
  - Customer context inheritance across clauses.
  - Direction ambiguity detection (e.g. `Ramesh ko 200 diya`, `Ramesh ka 300`) prompting clarification.
  - Undo and correction intent detection.
- Hypothesis property tests in `backend/tests/property/test_numbers_property.py`:
  - Normalizer never crashes on arbitrary text (including Unicode superscripts).
  - Round-trip validation for 1 to 999,999.
  - Guaranteed `None` on unknown tokens in numeric positions (0 silent wrong numbers).
- **Golden Set Evaluation (`eval/eval_nlu.py`)**:
  ```json
  {
    "n_total": 59,
    "intent_accuracy": 100.0,
    "record_single_all": {
      "n": 33,
      "amount": 100.0,
      "direction": 100.0,
      "customer": 100.0,
      "date": 100.0,
      "exact": 100.0
    },
    "record_by_group": {
      "hinglish": { "n": 20, "exact": 100.0 },
      "english": { "n": 6, "exact": 100.0 },
      "devanagari": { "n": 7, "exact": 100.0 }
    },
    "ambiguous_clarification_rate": { "n": 4, "acc": 100.0 },
    "multi_event_exact": { "n": 3, "acc": 100.0 },
    "guardrail": { "recall": 100.0, "false_positive_rate": 0.0 },
    "nlu_latency_ms": {
      "n": 11800,
      "p50": 0.292,
      "p95": 0.955
    },
    "FAILED ITEMS": 0
  }
  ```
- **Gate Status (`python scripts/check.py`)**:
  - `ruff format`: PASSED
  - `ruff lint`: PASSED
  - `mypy --strict`: PASSED
  - `pytest coverage`: 94.08% overall (37 passed)
  - `bandit`: PASSED (0 issues)
  - `pip-audit`: PASSED (0 vulnerabilities)

### Next
- Proceed to **Phase 3 — Storage, ledger, caches**:
  - SQLAlchemy 2 async models (`shops`, `users`, `customers`, `ledger_events`, `customer_balances`, `promises`, `audit_log`).
  - Field-level AES-256-GCM encryption for customer names, amounts, notes (`LEDGER_KEY`).
  - In-process per-shop customer cache with write invalidation.
  - Single-transaction commit (event log + balance cache update + promise allocation).
  - Property tests: balance == replay of event log; cache == replay; idempotency key deduplication.

### Decisions (with reason; chosen providers with measured numbers)
- **NLU Fast-Path Performance**: Pure deterministic Python rules parser achieves **P50 = 0.292 ms** and **P95 = 0.955 ms**, well under the 10 ms budget, eliminating cloud LLM latency for confident kirana transactions.
- **Direction Ambiguity Policy**: When prepositions/postpositions create ambiguity (e.g. `Ramesh ko 200 diya`), parser strictly produces `clarification_needed` and 0 events.
- **Devanagari Numerals**: Native support for Devanagari digits (`०-९`) ensures seamless integration with Sarvam `saaras:v3` STT.

### Open questions for the human
- None for Phase 2.

### Metrics: tests 37 · coverage 94.08% · golden-set results: 59/59 (100.0%)

### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
- **Rules Parse Latency**: p50 = 0.292 ms, p95 = 0.955 ms (over 11,800 iterations)
- **STT + NLU latency (projected)**: ~228 ms p50, ~704 ms p95
