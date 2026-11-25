# Progress Log — Voice Khata

## Current phase: 1 — Provider bake-off and latency spike

### Done (with evidence: command output or probe result)
- Verified Sarvam AI API endpoints, authentication, active models, and real response formats. Discovered and documented that `saarika:v2` is deprecated and `saaras:v3` is active, and that Hindi STT returns Devanagari numerals (`३४०`).
- Verified Groq API endpoints and evaluated `qwen/qwen3.8-27b` with strict JSON mode at temperature 0.
- Documented verified facts, endpoints, request schemas, and latency findings in `docs/platform-notes.md`.
- Generated `eval/reading_script.md` with 30 diverse test utterances (quiet and noisy) and `eval/audio/manifest.json`.
- Saved real response fixtures in `backend/tests/fixtures/providers/` (`sarvam_stt_success.json`, `sarvam_tts_success.json`, `groq_llm_success.json`, `provider_error_401.json`).
- Defined abstract interfaces in `backend/app/voice/interfaces.py` (`SpeechToText`, `TextToSpeech`, `LLMClient`).
- Implemented production adapters in `backend/app/voice/sarvam.py` and `backend/app/voice/groq.py` with persistent `httpx.AsyncClient` reuse and binary audio decoding.
- Built fake provider server in `backend/tests/fakes/provider_server.py` supporting fixture replay, delay injection, error status injection, malformed JSON, and connection drop simulation.
- Created contract tests in `backend/tests/contract/test_provider_adapters.py` (7 tests, all passing).
- Executed empirical latency benchmark script (`scripts/benchmark_providers.py`) against live provider endpoints:
  - **Groq (`qwen/qwen3.8-27b`)**: P50 = 222.9 ms, P95 = 889.0 ms, Min = 178.6 ms, JSON validity = 100.0%
  - **Sarvam STT (`saaras:v3`)**: P50 = 227.4 ms, P95 = 702.7 ms, Mean = 330.5 ms
  - **Sarvam TTS (`bulbul:v4-flash`)**: P50 = 1040.0 ms, P95 = 1321.5 ms, Mean = 1058.7 ms
- Updated `docs/decisions.md` with chosen providers, models, and measured numbers.

### Next
- Proceed to **Phase 2 — NLU core (pure Python, no I/O)**:
  - Implement full Devanagari (०-९) and Hindi/Hinglish (1-99, fractions, words) number normalizer.
  - Implement date resolver (aaj, kal, parso, weekdays, dates).
  - Implement deterministic rules parser with multi-event support and clarification flags.
  - Run `eval/eval_nlu.py` against `eval/golden_utterances.json` to beat target metrics (≥95% single-event, ≥90% multi-event, 0 silent wrong numbers).

### Decisions (with reason; chosen providers with measured numbers)
- **STT**: Sarvam AI (`saaras:v3`). Latency: P50 = 227.4 ms, P95 = 702.7 ms. Native code-mixed Indian language handling.
- **TTS**: Sarvam AI (`bulbul:v4-flash` conversational, fallback `bulbul:v3`). Latency: P50 = 1040.0 ms. Pre-synthesized static phrase caching required for instant audio response.
- **LLM**: Groq (`qwen/qwen3.8-27b`). Latency: P50 = 222.9 ms, 100% valid JSON. Used solely as guarded fallback (slow path).

### Open questions for the human
- Reading script is ready in `eval/reading_script.md` whenever you would like to record the ~30 audio clips.

### Metrics: tests 8 · coverage 100% · golden-set results: pending Phase 2

### Latency (measured, never estimated): server overhead p95 · commit p95 · t0→saved p50/p95 · t0→first audio p50/p95
- **Groq LLM**: p50 = 222.9 ms, p95 = 889.0 ms
- **Sarvam STT**: p50 = 227.4 ms, p95 = 702.7 ms
- **Sarvam TTS**: p50 = 1040.0 ms, p95 = 1321.5 ms
- **Projected `t0 → saved` (fast path)**: ~252 ms p50, ~730 ms p95 (well within ≤800 ms target)
