"""Fake provider server for contract and unit testing."""

import asyncio
import json
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "providers"


class FakeProviderHandler:
    """Mock HTTP transport handler replaying fixtures and injecting chaos."""

    def __init__(
        self,
        delay_ms: float = 0.0,
        inject_status: int | None = None,
        inject_malformed: bool = False,
        inject_drop: bool = False,
    ) -> None:
        self.delay_ms = delay_ms
        self.inject_status = inject_status
        self.inject_malformed = inject_malformed
        self.inject_drop = inject_drop
        self.call_count = 0

    async def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        if self.inject_drop:
            raise httpx.ConnectError("Connection dropped by fake provider", request=request)

        if self.inject_status:
            error_data = {"error": f"Injected error status {self.inject_status}"}
            return httpx.Response(self.inject_status, json=error_data, request=request)

        if self.inject_malformed:
            return httpx.Response(200, text="NOT_VALID_JSON{", request=request)

        path = request.url.path
        if "/speech-to-text" in path:
            fixture = json.loads(
                (FIXTURES_DIR / "sarvam_stt_success.json").read_text(encoding="utf-8")
            )
            return httpx.Response(200, json=fixture, request=request)

        if "/text-to-speech" in path:
            fixture = json.loads(
                (FIXTURES_DIR / "sarvam_tts_success.json").read_text(encoding="utf-8")
            )
            return httpx.Response(200, json=fixture, request=request)

        if "/chat/completions" in path:
            fixture = json.loads(
                (FIXTURES_DIR / "groq_llm_success.json").read_text(encoding="utf-8")
            )
            return httpx.Response(200, json=fixture, request=request)

        return httpx.Response(404, json={"error": "Not Found in fake provider"}, request=request)


def create_fake_client(
    delay_ms: float = 0.0,
    inject_status: int | None = None,
    inject_malformed: bool = False,
    inject_drop: bool = False,
) -> httpx.AsyncClient:
    handler = FakeProviderHandler(
        delay_ms=delay_ms,
        inject_status=inject_status,
        inject_malformed=inject_malformed,
        inject_drop=inject_drop,
    )
    transport = httpx.MockTransport(handler.handle_request)
    return httpx.AsyncClient(transport=transport, base_url="http://fake-provider")
