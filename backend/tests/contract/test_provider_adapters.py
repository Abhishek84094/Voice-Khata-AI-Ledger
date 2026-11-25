"""Contract tests for Sarvam STT, Sarvam TTS, and Groq LLM adapters."""

import json

import httpx
import pytest
from app.voice.groq import GroqLLMAdapter
from app.voice.sarvam import SarvamSTTAdapter, SarvamTTSAdapter
from tests.fakes.provider_server import create_fake_client


@pytest.mark.asyncio
async def test_sarvam_stt_adapter_success() -> None:
    client = create_fake_client()
    adapter = SarvamSTTAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    transcript = await adapter.transcribe(b"FAKE_AUDIO_BYTES", language_code="hi-IN")
    assert transcript == "रमेश का ३४० उधार।"
    await adapter.aclose()


@pytest.mark.asyncio
async def test_sarvam_stt_adapter_inject_error() -> None:
    client = create_fake_client(inject_status=401)
    adapter = SarvamSTTAdapter(api_key="bad-key", client=client, base_url="http://fake-provider")

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await adapter.transcribe(b"FAKE_AUDIO_BYTES")
    assert exc_info.value.response.status_code == 401
    await adapter.aclose()


@pytest.mark.asyncio
async def test_sarvam_tts_adapter_success() -> None:
    client = create_fake_client()
    adapter = SarvamTTSAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    audio_bytes = await adapter.synthesize("रमेश का ₹340 उधार. हो गया.", language_code="hi-IN")
    assert len(audio_bytes) > 0
    # First 4 bytes of RIFF WAV header
    assert audio_bytes[:4] == b"RIFF"
    await adapter.aclose()


@pytest.mark.asyncio
async def test_sarvam_tts_adapter_missing_audios() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"audios": []}, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fake-provider"
    )
    adapter = SarvamTTSAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    with pytest.raises(RuntimeError, match="returned no audio"):
        await adapter.synthesize("test")
    await adapter.aclose()


@pytest.mark.asyncio
async def test_groq_llm_adapter_success() -> None:
    client = create_fake_client()
    adapter = GroqLLMAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    result = await adapter.complete_json("Ramesh ka 340 udhaar", system_prompt="Parse transaction")
    assert result["intent"] == "record"
    assert result["events"][0]["customer"] == "Ramesh"
    assert result["events"][0]["amount"] == 340
    await adapter.aclose()


@pytest.mark.asyncio
async def test_groq_llm_adapter_malformed_json() -> None:
    client = create_fake_client(inject_malformed=True)
    adapter = GroqLLMAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    with pytest.raises(json.JSONDecodeError):
        await adapter.complete_json("test prompt")
    await adapter.aclose()


@pytest.mark.asyncio
async def test_provider_adapter_connection_drop() -> None:
    client = create_fake_client(inject_drop=True)
    adapter = GroqLLMAdapter(api_key="fake-key", client=client, base_url="http://fake-provider")

    with pytest.raises(httpx.ConnectError):
        await adapter.complete_json("test prompt")
    await adapter.aclose()
