"""Black-box probe of /ws/voice (fake STT/TTS) + REST: does a spoken entry reach the ledger?"""

import base64
import os
import secrets
import sys
import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

d = tempfile.mkdtemp()
os.environ.update(
    GNANI_API_KEY="probe",
    GROQ_API_KEY="",
    APP_ENV="test",
    DB_PATH=os.path.join(d, "probe.db"),
    LEDGER_KEY=base64.b64encode(secrets.token_bytes(32)).decode(),
)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class Sess:
    def __init__(self, t: str) -> None:
        self.t = t

    async def __aenter__(self) -> "Sess":
        return self

    async def __aexit__(self, *a: Any) -> None:
        pass

    async def send_audio(self, f: bytes) -> None:
        pass

    async def finish(self, timeout: float = 12.0) -> str:
        return self.t


class Cli:
    def __init__(self, t: str) -> None:
        self.t = t

    def session(self, language: str = "") -> Sess:
        return Sess(self.t)


def run(client: TestClient, text: str) -> tuple[str, list[tuple[str, str]]]:
    with (
        patch("app.api.ws_voice._run_tts", AsyncMock()),
        patch("app.voice.stt_client.GnaniSTTClient", lambda **kw: Cli(text)),
    ):
        with client.websocket_connect("/ws/voice") as ws:
            first = ws.receive_json()
            ws.send_json({"type": "start", "language": "hi-IN"})
            ws.receive_json()
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit"})
            msgs = []
            for _ in range(4):
                try:
                    m = ws.receive_json()
                    msgs.append(m)
                    if m["type"] not in ("transcript_final",):
                        break
                except Exception:
                    break
            return first["type"], [(m["type"], str(m.get("text", ""))[:60]) for m in msgs]


def run_session(
    client: TestClient, utterances: list[str]
) -> list[tuple[str, list[tuple[str, str]]]]:
    results = []
    with patch("app.api.ws_voice._run_tts", AsyncMock()):
        with client.websocket_connect("/ws/voice") as ws:
            first = ws.receive_json()
            for text in utterances:
                with patch("app.voice.stt_client.GnaniSTTClient", lambda t=text, **kw: Cli(t)):
                    ws.send_json({"type": "start", "language": "hi-IN"})
                    ws.receive_json()
                    ws.send_bytes(b"\x00" * 3200)
                    ws.send_json({"type": "commit"})
                    msgs = []
                    for _ in range(5):
                        try:
                            m = ws.receive_json()
                            msgs.append(m)
                            if m["type"] in ("saved", "clarify", "cancelled"):
                                break
                        except Exception:
                            break
                    results.append(
                        (first["type"], [(m["type"], str(m.get("text", ""))[:60]) for m in msgs])
                    )
    return results


def main() -> None:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        # Start with clean slate for default shop
        c.delete("/api/data")
        for t in [
            "Ramesh ka 340 udhaar",
            "Suresh ne 500 diye",
            "last entry hata do",
            "Ramesh ka total?",
            "nahi 430",
            "Ramesh ka 340 udhaar, kal 200 diya tha",
        ]:
            print(repr(t), "->", run(c, t))

        # Phase 5 multi-turn probe:
        # Speak full-amount promise, then "isne abhi 800 diye",
        # check reduced balance, PARTIALLY_KEPT, saved note
        print("\n--- Phase 5 Promise & Partial Payment Probe ---")
        sess_results = run_session(
            c,
            [
                "Ramesh ka 2000 udhaar, agle hafte dega",
                "isne abhi 800 diye, salary late aayi",
            ],
        )
        for idx, res in enumerate(sess_results):
            print(f"Turn {idx + 1} ->", res)

        led = c.get("/api/ledger")
        cus = c.get("/api/customers")
        proms = c.get("/api/promises")

        print("GET /api/ledger ->", led.status_code, "events stored:", len(led.json()))
        print("GET /api/customers ->", cus.status_code, "customers stored:", len(cus.json()))
        print("GET /api/promises ->", proms.status_code, "promises stored:", len(proms.json()))
        if proms.status_code == 200 and proms.json():
            p_data = proms.json()[0]
            print(
                f"Verified Promise -> Customer: {p_data.get('customer_name')}, "
                f"Status: {p_data.get('status')}, Remaining: {p_data.get('remaining_paise')} paise"
            )
            assert p_data.get("status") == "PARTIALLY_KEPT"
            assert p_data.get("remaining_paise") == 120000  # ₹1200 remaining

        # Verify saved note on payment
        if led.status_code == 200 and led.json():
            notes = [e.get("note") for e in led.json() if e.get("note")]
            print("Verified Saved Notes in Ledger:", notes)
            assert any("salary late aayi" in (n or "") for n in notes)

        # Phase 6 query probe:
        # Ask spoken queries via voice and verify answers match report endpoints
        print("\n--- Phase 6 Query Engine Probe ---")
        q_results = run_session(
            c,
            [
                "Ramesh ka total?",
                "is hafte kitna udhaar gaya?",
            ],
        )
        for idx, res in enumerate(q_results):
            print(f"Query Turn {idx + 1} ->", res)

        rep_summary = c.get("/api/reports/summary?period=this_week")
        print(
            "GET /api/reports/summary?period=this_week ->",
            rep_summary.status_code,
            rep_summary.json(),
        )
        assert rep_summary.status_code == 200

        rep_debtors = c.get("/api/reports/top-debtors")
        print("GET /api/reports/top-debtors ->", rep_debtors.status_code, rep_debtors.json())
        assert rep_debtors.status_code == 200

        print("DELETE /api/data without any credentials ->", c.delete("/api/data").status_code)
        print("GET /api/export without any credentials ->", c.get("/api/export").status_code)


if __name__ == "__main__":
    main()
