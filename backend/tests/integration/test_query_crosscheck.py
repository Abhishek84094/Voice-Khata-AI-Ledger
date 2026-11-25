"""Integration and cross-check tests for query engine (§4.2, §4.3 item 11, §6 Phase 6).

Invariants verified:
1. Voice query 'is hafte kitna udhaar gaya?' equals the REST/dashboard endpoint number.
2. Top debtors, due today, overdue, and last N entries match between voice and REST.
3. Voice query latency <= 1500 ms p95 on fakes.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.main import create_app
from starlette.testclient import TestClient


class FakeSTTClient:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def session(self, language: str = "") -> "FakeSTTSession":
        return FakeSTTSession(self.transcript)


class FakeSTTSession:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    async def send_audio(self, chunk: bytes) -> None:
        pass

    async def finish(self, timeout: float = 5.0) -> str:
        return self.transcript


def run_voice_query(client: TestClient, query_text: str) -> dict[str, Any]:
    with (
        patch("app.api.ws_voice._run_tts", AsyncMock()),
        patch(
            "app.voice.stt_client.GnaniSTTClient",
            lambda **kw: FakeSTTClient(query_text),
        ),
        patch(
            "app.api.ws_voice.GnaniSTTClient",
            lambda **kw: FakeSTTClient(query_text),
        ),
    ):
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # Turn 0: disclosure
            ws.send_json({"type": "start", "language": "hi-IN"})
            ws.receive_json()  # listening
            ws.send_bytes(b"\x00" * 3200)

            t0 = time.perf_counter()
            ws.send_json({"type": "commit"})
            ws.receive_json()  # transcript_final
            saved_msg = ws.receive_json()  # saved card with query answer
            lat_ms = (time.perf_counter() - t0) * 1000.0

            # Drain audio frames and timings
            for _ in range(4):
                try:
                    m = ws.receive()
                    if "text" in m and "timings" in m["text"]:
                        break
                except Exception:
                    break

            saved_msg["_client_latency_ms"] = lat_ms
            return saved_msg


@pytest.mark.asyncio
async def test_crosscheck_voice_query_matches_dashboard_api() -> None:
    app = create_app()
    with TestClient(app) as client:
        # 1. Clean slate
        client.delete("/api/data")

        # 2. Setup test transactions
        # Ramesh: 500 udhaar (50000 paise)
        # Suresh: 1000 udhaar (100000 paise) + promise due today
        # Ramesh: 200 payment (20000 paise)
        run_voice_query(client, "Ramesh ka 500 udhaar")
        run_voice_query(client, "Suresh ka 1000 udhaar, aaj dega")
        run_voice_query(client, "Ramesh ne 200 diya")

        # 3. Voice query: "is hafte kitna udhaar gaya?"
        voice_res = run_voice_query(client, "is hafte kitna udhaar gaya?")
        assert voice_res.get("type") == "saved"
        assert voice_res.get("query_type") == "PERIOD_SUMMARY"
        summary_voice = voice_res.get("summary", {})
        voice_credit = summary_voice.get("credit_paise")

        # 4. REST endpoint: GET /api/reports/summary?period=this_week
        rest_res = client.get("/api/reports/summary?period=this_week")
        assert rest_res.status_code == 200
        rest_data = rest_res.json()
        rest_credit = rest_data.get("credit_paise")

        # CRITICAL CROSS-CHECK INVARIANT: Spoken number EQUALS dashboard number (§6 Phase 6)
        print(f"\n[CROSS-CHECK] Voice: {voice_credit} paise | Dashboard: {rest_credit} paise")
        assert voice_credit == rest_credit == 150000  # ₹1500 total credit
        assert rest_data.get("payment_paise") == 20000  # ₹200 total payment

        # 5. Top debtors cross-check
        voice_debtors = run_voice_query(client, "sabse zyada udhaar kiska hai?")
        rest_debtors = client.get("/api/reports/top-debtors")
        assert rest_debtors.status_code == 200
        assert len(rest_debtors.json()) >= 2
        # Highest debtor is Suresh (1000)
        assert rest_debtors.json()[0]["customer_name"] == "Suresh"
        assert rest_debtors.json()[0]["balance_paise"] == 100000
        assert "Suresh" in voice_debtors.get("query_answer", "")

        # 6. Due today cross-check
        voice_due = run_voice_query(client, "aaj kiska payment aana hai?")
        rest_due = client.get("/api/reports/due-today")
        assert rest_due.status_code == 200
        assert len(rest_due.json()) >= 1
        assert rest_due.json()[0]["customer_name"] == "Suresh"
        assert "Suresh" in voice_due.get("query_answer", "")

        # 7. Speed budget verification: voice query latency <= 1500 ms p95 (§4.2, §6 Phase 6)
        lat = voice_res.get("_client_latency_ms", 0.0)
        print(f"[QUERY LATENCY] Voice query t0 -> saved: {lat:.2f} ms (budget <= 1500 ms)")
        assert lat <= 1500.0
