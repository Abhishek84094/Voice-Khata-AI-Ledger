"""STT streaming client adapters (§3.2, §4.3)."""

import io
import wave
from typing import Any

import httpx
from app.core.config import get_settings
from app.voice.sarvam import SarvamSTTAdapter


class StreamingSTTSession:
    """Session interface for streaming audio frames to STT."""

    def __init__(self, language: str = "hi-IN") -> None:
        self.language = language
        self.audio_chunks: list[bytes] = []

    async def __aenter__(self) -> "StreamingSTTSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def send_audio(self, frame: bytes) -> None:
        self.audio_chunks.append(frame)

    async def finish(self, timeout: float = 12.0) -> str:
        """Combine accumulated PCM16 frames into a WAV buffer and transcribe."""
        if not self.audio_chunks:
            return ""

        pcm_data = b"".join(self.audio_chunks)
        # Wrap raw PCM16 (16kHz mono) in WAV container for HTTP STT endpoints
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm_data)
        wav_bytes = buf.getvalue()

        # Call Sarvam STT
        settings = get_settings()
        api_key = settings.sarvam_api_key
        if not api_key:
            return ""

        async with httpx.AsyncClient(timeout=timeout) as client:
            stt = SarvamSTTAdapter(api_key=api_key, client=client)
            return await stt.transcribe(wav_bytes, language_code=self.language)


class SarvamSTTClient:
    """Sarvam STT client factory creating per-utterance sessions."""

    def __init__(self, api_key: str = "", **kwargs: Any) -> None:
        self.api_key = api_key or get_settings().sarvam_api_key

    def session(self, language: str = "hi-IN") -> StreamingSTTSession:
        return StreamingSTTSession(language=language)


# Alias GnaniSTTClient to allow seamless mocking in eval/probe_pipeline.py
GnaniSTTClient = SarvamSTTClient
