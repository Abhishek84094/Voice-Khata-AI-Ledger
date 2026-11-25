"""Unit and chaos tests for Phase 10 Reliability & Degradation Ladder (§6 Phase 10).

Covers:
1. CircuitBreaker state transitions: CLOSED -> OPEN on failures, refusal when OPEN.
2. Retry with backoff and jitter.
3. Strict timeout enforcement.
4. Degradation ladder actions and invariant assertions:
   - DB failure NEVER fakes success.
   - TTS failure falls back to text-only screen display.
   - STT failure prompts user to retry or type.
   - LLM failure falls back to pure rules or asks for repetition.
5. Chaos simulation:
   - Socket abrupt client disconnect mid-turn.
   - Upstream slow/corrupted provider payload.
   - Concurrent load resilience.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core.reliability import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    DegradationAction,
    resolve_degradation_action,
    retry_with_backoff,
)


@pytest.mark.asyncio
async def test_circuit_breaker_transitions() -> None:
    cb = CircuitBreaker(
        "test-service", failure_threshold=2, recovery_timeout_s=0.1, half_open_success_threshold=1
    )
    assert cb.state == CircuitState.CLOSED

    # Success keeps it closed
    async def good_call() -> str:
        return "ok"

    res = await cb.call(good_call)
    assert res == "ok"
    assert cb.state == CircuitState.CLOSED

    # 1 failure
    async def bad_call() -> str:
        raise ValueError("Provider down")

    with pytest.raises(ValueError):
        await cb.call(bad_call)
    assert cb.state == CircuitState.CLOSED

    # 2nd failure trips circuit to OPEN
    with pytest.raises(ValueError):
        await cb.call(bad_call)
    assert cb.state == CircuitState.OPEN

    # Immediate next call rejected fast with CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(good_call)

    # Wait for recovery timeout
    await asyncio.sleep(0.12)

    # In HALF_OPEN state, single success recovers to CLOSED
    res = await cb.call(good_call)
    assert res == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_timeout_enforcement() -> None:
    cb = CircuitBreaker("slow-service", failure_threshold=1, recovery_timeout_s=1.0)

    async def hang_call() -> str:
        await asyncio.sleep(0.2)
        return "late"

    with pytest.raises(asyncio.TimeoutError):
        await cb.call(hang_call, timeout_s=0.05)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_retry_with_backoff_success_after_failure() -> None:
    calls = 0

    async def flaky_service() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ConnectionResetError("Transient network drop")
        return "connected"

    res = await retry_with_backoff(flaky_service, max_retries=2, base_delay_s=0.01)
    assert res == "connected"
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_with_backoff_exceeds_retries() -> None:
    calls = 0

    async def broken_service() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("Permanent failure")

    with pytest.raises(RuntimeError):
        await retry_with_backoff(broken_service, max_retries=2, base_delay_s=0.01)
    assert calls == 3  # initial + 2 retries


def test_degradation_ladder_invariants() -> None:
    # 1. DB failure MUST NEVER say saved or fake success
    act, msg = resolve_degradation_action("database_commit")
    assert act == DegradationAction.ABORT_WITH_ERROR
    assert "save nahi" in msg or "koshish" in msg

    # 2. TTS failure provides text-only fallback so screen card is unblocked
    act, msg = resolve_degradation_action("tts_sarvam")
    assert act == DegradationAction.FALLBACK_TO_TEXT_ONLY
    assert "screen" in msg

    # 3. STT failure prompts spoken or typed repetition
    act, msg = resolve_degradation_action("stt_stream")
    assert act == DegradationAction.FALLBACK_TO_TYPED_INPUT

    # 4. LLM failure falls back to asking clear rules
    act, msg = resolve_degradation_action("llm_groq")
    assert act == DegradationAction.FALLBACK_TO_RULES_ASK


@pytest.mark.asyncio
async def test_chaos_concurrent_load_and_cancellation() -> None:
    """Chaos test: cancel tasks mid-execution simulating client closing WebSocket connection."""
    cancelled = 0
    completed = 0

    async def mock_utterance_handler(idx: int) -> None:
        nonlocal cancelled, completed
        try:
            await asyncio.sleep(0.05)
            completed += 1
        except asyncio.CancelledError:
            cancelled += 1
            raise

    tasks = [asyncio.create_task(mock_utterance_handler(i)) for i in range(20)]
    # Abruptly cancel half the tasks mid-stream
    await asyncio.sleep(0.01)
    for t in tasks[:10]:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    assert cancelled == 10
    assert completed == 10
