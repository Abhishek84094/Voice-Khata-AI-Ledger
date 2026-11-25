"""Sarvam AI adapters for STT and TTS."""

import base64

import httpx
from app.voice.interfaces import SpeechToText, TextToSpeech


class SarvamSTTAdapter(SpeechToText):
    """Sarvam AI Speech-to-Text adapter using saaras:v3 model."""

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.sarvam.ai",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = client is None

    async def transcribe(self, audio_bytes: bytes, language_code: str = "hi-IN") -> str:
        url = f"{self.base_url}/speech-to-text"
        headers = {"api-subscription-key": self.api_key}
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        data = {
            "model": "saaras:v3",
            "language_code": language_code,
            "with_diarization": "false",
        }

        response = await self._client.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("transcript", ""))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class SarvamTTSAdapter(TextToSpeech):
    """Sarvam AI Text-to-Speech adapter using bulbul:v4-flash or bulbul:v3 model."""

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.sarvam.ai",
        default_model: str = "bulbul:v4-flash",
        default_speaker: str = "amit_hi_conversational",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.default_speaker = default_speaker
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = client is None

    async def synthesize(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: str | None = None,
    ) -> bytes:
        url = f"{self.base_url}/text-to-speech"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        chosen_speaker = speaker or self.default_speaker
        body = {
            "inputs": [text],
            "target_language_code": language_code,
            "speaker": chosen_speaker,
            "model": self.default_model,
        }

        response = await self._client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
        audios = payload.get("audios", [])
        if not audios:
            raise RuntimeError("Sarvam TTS returned no audio chunks")
        return base64.b64decode(audios[0])

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
