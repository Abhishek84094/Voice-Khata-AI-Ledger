"""Abstract provider interfaces for Speech-to-Text, Text-to-Speech, and LLM."""

from abc import ABC, abstractmethod
from typing import Any


class SpeechToText(ABC):
    """Interface for speech-to-text transcription."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language_code: str = "hi-IN") -> str:
        """Transcribe speech audio to text."""
        ...


class TextToSpeech(ABC):
    """Interface for text-to-speech audio synthesis."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language_code: str = "hi-IN",
        speaker: str | None = None,
    ) -> bytes:
        """Synthesize text to raw binary audio bytes (WAV/PCM)."""
        ...


class LLMClient(ABC):
    """Interface for low-latency JSON completions."""

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON output from LLM with strict temperature 0."""
        ...
