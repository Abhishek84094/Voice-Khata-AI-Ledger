"""Unit tests for STT streaming session interface."""

import pytest
from app.voice.stt_client import SarvamSTTClient, StreamingSTTSession


@pytest.mark.asyncio
async def test_streaming_stt_session_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    from app.voice.sarvam import SarvamSTTAdapter

    monkeypatch.setattr(SarvamSTTAdapter, "transcribe", AsyncMock(return_value="test transcript"))

    sess = StreamingSTTSession(language="hi-IN")
    async with sess as s:
        assert s.language == "hi-IN"
        await s.send_audio(b"\x00\x01" * 160)
        assert len(s.audio_chunks) == 1

        res = await s.finish()
        assert res == "test transcript"


def test_sarvam_stt_client_creation() -> None:
    cli = SarvamSTTClient(api_key="test_key")
    sess = cli.session(language="kn-IN")
    assert sess.language == "kn-IN"
