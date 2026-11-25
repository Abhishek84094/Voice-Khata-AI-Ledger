"""Unit tests for VoiceSession state machine."""

from app.dialogue.session import SessionState, VoiceSession


def test_session_lifecycle() -> None:
    session = VoiceSession(language="hi-IN")
    assert session.state == SessionState.IDLE
    assert len(session.audio_buffer) == 0

    session.start_utterance("hi-IN")
    assert session.state == SessionState.LISTENING

    session.append_audio(b"\x00\x01" * 100)
    assert len(session.audio_buffer) == 200

    t0 = session.commit_utterance()
    assert session.state == SessionState.PROCESSING
    assert t0 > 0.0

    session.update_context(
        customer_id="cust_123",
        customer_name="Ramesh",
        last_event_id="evt_456",
        last_amount_paise=34000,
        action="record",
    )
    assert session.state == SessionState.IDLE
    assert session.current_customer_name == "Ramesh"
    assert session.last_event_id == "evt_456"
    assert session.last_event_amount_paise == 34000
