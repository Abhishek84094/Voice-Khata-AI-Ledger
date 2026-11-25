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


def main() -> None:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        for t in [
            "Ramesh ka 340 udhaar",
            "Suresh ne 500 diye",
            "last entry hata do",
            "Ramesh ka total?",
            "nahi 430",
            "Ramesh ka 340 udhaar, kal 200 diya tha",
        ]:
            print(repr(t), "->", run(c, t))
        led = c.get("/api/ledger")
        cus = c.get("/api/customers")
        print("GET /api/ledger ->", led.status_code, "events stored:", len(led.json()))
        print("GET /api/customers ->", cus.status_code, "customers stored:", len(cus.json()))
        print("DELETE /api/data without any credentials ->", c.delete("/api/data").status_code)
        print("GET /api/export without any credentials ->", c.get("/api/export").status_code)


if __name__ == "__main__":
    main()
