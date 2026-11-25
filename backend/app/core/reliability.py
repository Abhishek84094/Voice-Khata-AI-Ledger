"""Reliability primitives for Voice Khata (§6 Phase 10).

Features:
1. CircuitBreaker pattern (CLOSED, OPEN, HALF_OPEN) with failure thresholds and recovery timeout.
2. Async retry with exponential backoff and jitter.
3. Strict stage timeouts:
   - STT stream/finalization: <= 800 ms
   - LLM completion: <= 1200 ms
   - TTS synthesis: <= 800 ms
   - DB commit: <= 50 ms
4. Degradation Ladder (§6 Phase 10):
   - STT fails -> fallback to typed input prompt or instant retry prompt.
   - TTS fails -> fallback to text card + sound cue chime, never block card.
   - LLM fails -> fallback to pure rules parser; if unsure, ask shopkeeper to repeat.
   - DB fails -> explicitly inform failure; NEVER fake success or confirm uncommitted entries.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while the circuit is OPEN."""

    def __init__(self, service_name: str, retry_after_s: float) -> None:
        super().__init__(
            f"Circuit breaker for '{service_name}' is OPEN. Retry after {retry_after_s:.1f}s"
        )
        self.service_name = service_name
        self.retry_after_s = retry_after_s


class CircuitBreaker:
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 10.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.opened_at: float | None = None

    def _update_state(self, now: float) -> None:
        if self.state == CircuitState.OPEN and self.opened_at is not None:
            if now - self.opened_at >= self.recovery_timeout_s:
                self.state = CircuitState.HALF_OPEN
                self.consecutive_successes = 0
                logger.info(f"Circuit '{self.service_name}' transitioning from OPEN to HALF_OPEN")

    def record_success(self) -> None:
        now = time.monotonic()
        self._update_state(now)

        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.half_open_success_threshold:
                self.state = CircuitState.CLOSED
                self.consecutive_failures = 0
                self.consecutive_successes = 0
                self.opened_at = None
                logger.info(f"Circuit '{self.service_name}' CLOSED (recovered)")
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        now = time.monotonic()
        self._update_state(now)

        self.consecutive_failures += 1
        if (
            self.state == CircuitState.HALF_OPEN
            or self.consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = now
            logger.warning(
                f"Circuit '{self.service_name}' is now OPEN (failures: {self.consecutive_failures})"
            )

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> T:
        now = time.monotonic()
        self._update_state(now)

        if self.state == CircuitState.OPEN:
            elapsed = now - (self.opened_at or now)
            remaining = max(0.0, self.recovery_timeout_s - elapsed)
            raise CircuitBreakerOpenError(self.service_name, remaining)

        try:
            if timeout_s is not None and timeout_s > 0:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
            else:
                result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


async def retry_with_backoff(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 2,
    base_delay_s: float = 0.05,
    max_delay_s: float = 0.5,
    jitter: bool = True,
    **kwargs: Any,
) -> T:
    """Async retry helper with exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise exc
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            if jitter:
                # Use secrets for jitter to satisfy bandit CWE-330
                jitter_val = secrets.randbelow(1000) / 1000.0
                delay = delay * (0.5 + jitter_val * 0.5)
            await asyncio.sleep(delay)


class DegradationAction(str, enum.Enum):
    FALLBACK_TO_TYPED_INPUT = "FALLBACK_TO_TYPED_INPUT"
    FALLBACK_TO_TEXT_ONLY = "FALLBACK_TO_TEXT_ONLY"
    FALLBACK_TO_RULES_ASK = "FALLBACK_TO_RULES_ASK"
    ABORT_WITH_ERROR = "ABORT_WITH_ERROR"


def resolve_degradation_action(
    failed_component: str,
    error: Exception | None = None,
) -> tuple[DegradationAction, str]:
    """Determine client guidance according to the §6 Phase 10 degradation ladder.

    Guarantees:
    - Never fake success on DB failure.
    - Provide immediate text fallback on TTS failure.
    - Ask shopkeeper to clarify or type if STT or LLM fails.
    """
    comp = failed_component.lower()
    if "db" in comp or "database" in comp or "ledger" in comp:
        return (
            DegradationAction.ABORT_WITH_ERROR,
            "Entry save nahi ho paayi. Kripya dobara koshish karein.",
        )
    elif "stt" in comp or "audio" in comp or "transcription" in comp:
        return (
            DegradationAction.FALLBACK_TO_TYPED_INPUT,
            "Awaaz samajh nahi aayi. Bol kar ya likh kar dobara bataein.",
        )
    elif "tts" in comp or "voice" in comp or "synthesis" in comp:
        return (
            DegradationAction.FALLBACK_TO_TEXT_ONLY,
            "Awaaz uplabdh nahi hai, hisaab screen par darj hai.",
        )
    elif "llm" in comp or "ai" in comp:
        return (
            DegradationAction.FALLBACK_TO_RULES_ASK,
            "Kripya naam aur raqam saaf boleim (jaise: Ramesh 500 jama).",
        )
    return (DegradationAction.ABORT_WITH_ERROR, "Asuvidha ke liye khed hai. Dobara koshish karein.")
