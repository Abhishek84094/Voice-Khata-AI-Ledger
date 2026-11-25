"""Server overhead latency test (§4.2, §4.6: server overhead per utterance <= 50 ms p95)."""

import time
from typing import Any

import pytest
from app.main import create_app
from starlette.testclient import TestClient


class InstantSTTSession:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    async def __aenter__(self) -> "InstantSTTSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def send_audio(self, frame: bytes) -> None:
        pass

    async def finish(self, timeout: float = 12.0) -> str:
        return self.transcript


class InstantSTTClient:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def session(self, language: str = "hi-IN") -> InstantSTTSession:
        return InstantSTTSession(self.transcript)


def test_server_overhead_under_50ms_p95(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overhead test: fake STT/TTS with 0ms network delay (§4.2, §4.6)."""
    transcript = "Ramesh ka 340 udhaar"
    monkeypatch.setattr(
        "app.voice.stt_client.GnaniSTTClient", lambda **kw: InstantSTTClient(transcript)
    )
    monkeypatch.setattr(
        "app.api.ws_voice.GnaniSTTClient", lambda **kw: InstantSTTClient(transcript)
    )

    app = create_app()
    with TestClient(app) as client:
        client.delete("/api/data")

        latencies_ms: list[float] = []

        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # Turn 0: disclosure

            # Warmup 5 turns
            for w in range(5):
                ws.send_json({"type": "start", "language": "hi-IN"})
                ws.receive_json()
                ws.send_bytes(b"\x00" * 3200)
                ws.send_json({"type": "commit", "idempotency_key": f"warmup_{w}"})
                ws.receive_json()
                ws.receive_json()
                ws.receive_json()
                ws.receive_json()
                ws.receive_bytes()
                ws.receive_json()
                ws.receive_json()

            # Measure 300 utterances
            for i in range(300):
                ws.send_json({"type": "start", "language": "hi-IN"})
                ws.receive_json()  # listening
                ws.send_bytes(b"\x00" * 3200)

                t0 = time.perf_counter()
                ws.send_json({"type": "commit", "idempotency_key": f"perf_{i}"})
                ws.receive_json()  # transcript_final
                ws.receive_json()  # saving
                ws.receive_json()  # saved card visible
                dt_saved_ms = (time.perf_counter() - t0) * 1000.0

                ws.receive_json()  # audio_start
                ws.receive_bytes()  # audio
                ws.receive_json()  # audio_end
                ws.receive_json()  # timings

                # Overhead is total server processing time for commit -> saved card
                latencies_ms.append(dt_saved_ms)

        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
        min_lat = min(latencies_ms)
        max_lat = max(latencies_ms)

        print(
            f"\n[SERVER OVERHEAD PERF (300 runs)] P50: {p50:.2f}ms, P95: {p95:.2f}ms, "
            f"P99: {p99:.2f}ms, Min: {min_lat:.2f}ms, Max: {max_lat:.2f}ms"
        )

        # Budget: server overhead per utterance <= 50 ms p95 (§4.2, §4.6)
        assert p95 <= 50.0
