"""Voice session state machine (§4.3, §5.7)."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"


@dataclass
class VoiceSession:
    """Maintains conversational context across turns within a single WebSocket connection."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shop_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    language: str = "hi-IN"
    state: SessionState = SessionState.IDLE
    current_customer_id: str | None = None
    current_customer_name: str | None = None
    last_event_id: str | None = None
    last_event_amount_paise: int | None = None
    last_action: str | None = None
    pending_clarification: dict[str, Any] | None = None
    audio_buffer: bytearray = field(default_factory=bytearray)
    t0_perf: float = 0.0

    def start_utterance(self, language: str | None = None) -> None:
        if language:
            self.language = language
        self.state = SessionState.LISTENING
        self.audio_buffer.clear()
        self.t0_perf = 0.0

    def commit_utterance(self) -> float:
        self.state = SessionState.PROCESSING
        self.t0_perf = time.perf_counter()
        return self.t0_perf

    def append_audio(self, chunk: bytes) -> None:
        self.audio_buffer.extend(chunk)

    def update_context(
        self,
        customer_id: str | None = None,
        customer_name: str | None = None,
        last_event_id: str | None = None,
        last_amount_paise: int | None = None,
        action: str | None = None,
    ) -> None:
        if customer_id:
            self.current_customer_id = customer_id
        if customer_name:
            self.current_customer_name = customer_name
        if last_event_id:
            self.last_event_id = last_event_id
        if last_amount_paise is not None:
            self.last_event_amount_paise = last_amount_paise
        if action:
            self.last_action = action
        self.state = SessionState.IDLE
