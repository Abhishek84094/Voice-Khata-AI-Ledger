"""End-to-end WebSocket tests for the voice pipeline (§4.3, §4.4, §6 Phase 4)."""

from typing import Any

import pytest
from app.main import create_app
from starlette.testclient import TestClient


class FakeSTTSession:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    async def __aenter__(self) -> "FakeSTTSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def send_audio(self, frame: bytes) -> None:
        pass

    async def finish(self, timeout: float = 12.0) -> str:
        return self.transcript


class FakeSTTClient:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def session(self, language: str = "hi-IN") -> FakeSTTSession:
        return FakeSTTSession(self.transcript)


def test_full_voice_pipeline_credit_and_rest_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = "Ramesh ka 340 udhaar"
    monkeypatch.setattr("app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript))
    monkeypatch.setattr(
        "app.voice.stt_client.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript)
    )
    monkeypatch.setattr(
        "app.voice.stt_client.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript)
    )

    app = create_app()
    with TestClient(app) as client:
        # Purge existing data
        del_res = client.delete("/api/data")
        assert del_res.status_code == 200

        with client.websocket_connect("/ws/voice") as ws:
            # 1. Turn 0: AI disclosure turn
            first = ws.receive_json()
            assert first["type"] == "disclosure"
            assert "AI Munim" in first["text"]

            # 2. Start
            ws.send_json({"type": "start", "language": "hi-IN"})
            listening = ws.receive_json()
            assert listening["type"] == "listening"

            # 3. Stream binary PCM audio chunk
            ws.send_bytes(b"\x00\x01" * 1600)

            # 4. Commit
            ws.send_json({"type": "commit", "idempotency_key": "voice_test_key_1"})

            # 5. Receive transcript_final
            m_final = ws.receive_json()
            assert m_final["type"] == "transcript_final"
            assert m_final["text"] == "Ramesh ka 340 udhaar"

            # 6. Receive saving
            m_saving = ws.receive_json()
            assert m_saving["type"] == "saving"

            # 7. Receive saved
            m_saved = ws.receive_json()
            assert m_saved["type"] == "saved"
            assert m_saved["customer_name"] == "Ramesh"
            assert m_saved["balance_paise"] == 34000
            assert len(m_saved["events"]) == 1

            # 8. Receive TTS framing and audio chunk
            m_audio_start = ws.receive_json()
            assert m_audio_start["type"] == "audio_start"

            raw_audio = ws.receive_bytes()
            assert len(raw_audio) > 0

            m_audio_end = ws.receive_json()
            assert m_audio_end["type"] == "audio_end"

            # 9. Receive timings
            m_timings = ws.receive_json()
            assert m_timings["type"] == "timings"
            assert "stt_ms" in m_timings
            assert "commit_ms" in m_timings

        # 10. Verify REST visibility
        led_res = client.get("/api/ledger")
        assert led_res.status_code == 200
        events = led_res.json()
        assert len(events) == 1
        assert events[0]["customer_name"] == "Ramesh"
        assert events[0]["amount_paise"] == 34000

        cust_res = client.get("/api/customers")
        assert cust_res.status_code == 200
        customers = cust_res.json()
        assert len(customers) == 1
        assert customers[0]["display_name"] == "Ramesh"
        assert customers[0]["balance_paise"] == 34000


def test_voice_duplicate_commit_does_not_double_post(monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = "Ramesh ka 340 udhaar"
    monkeypatch.setattr("app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript))
    monkeypatch.setattr(
        "app.voice.stt_client.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript)
    )
    monkeypatch.setattr(
        "app.voice.stt_client.GnaniSTTClient", lambda **kw: FakeSTTClient(transcript)
    )

    app = create_app()
    with TestClient(app) as client:
        client.delete("/api/data")

        # First commit
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # disclosure
            ws.send_json({"type": "start", "language": "hi-IN"})
            ws.receive_json()  # listening
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit", "idempotency_key": "duplicate_key_test"})
            ws.receive_json()  # transcript_final
            ws.receive_json()  # saving
            res1 = ws.receive_json()  # saved
            assert res1["balance_paise"] == 34000
            ws.receive_json()  # audio_start
            ws.receive_bytes()  # audio
            ws.receive_json()  # audio_end
            ws.receive_json()  # timings

        # Second commit with duplicate idempotency key
        with client.websocket_connect("/ws/voice") as ws2:
            ws2.receive_json()  # disclosure
            ws2.send_json({"type": "start", "language": "hi-IN"})
            ws2.receive_json()  # listening
            ws2.send_bytes(b"\x00" * 3200)
            ws2.send_json({"type": "commit", "idempotency_key": "duplicate_key_test"})
            ws2.receive_json()  # transcript_final
            ws2.receive_json()  # saving
            res2 = ws2.receive_json()  # saved
            assert res2["balance_paise"] == 34000
            assert res2["events"][0]["is_duplicate"] is True

        # Check balance in DB remains 34000, not 68000
        cust_res = client.get("/api/customers")
        assert cust_res.json()[0]["balance_paise"] == 34000


def test_voice_undo_and_correction_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    with TestClient(app) as client:
        client.delete("/api/data")

        # 1. Entry: Ramesh ka 340 udhaar
        monkeypatch.setattr(
            "app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient("Ramesh ka 340 udhaar")
        )
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # disclosure
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit"})
            ws.receive_json()  # transcript_final
            ws.receive_json()  # saving
            s1 = ws.receive_json()  # saved
            assert s1["balance_paise"] == 34000
            ws.receive_json()  # audio_start
            ws.receive_bytes()  # audio
            ws.receive_json()  # audio_end
            ws.receive_json()  # timings

            # 2. Correction in same session: "nahi 430"
            monkeypatch.setattr(
                "app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient("nahi 430")
            )
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit"})
            ws.receive_json()  # transcript_final
            ws.receive_json()  # saving
            s2 = ws.receive_json()  # saved
            assert s2["action"] == "amended"
            assert s2["new_amount_paise"] == 43000
            assert s2["balance_paise"] == 43000
            ws.receive_json()  # audio_start
            ws.receive_bytes()  # audio
            ws.receive_json()  # audio_end
            ws.receive_json()  # timings

            # 3. Undo: "last entry hata do"
            monkeypatch.setattr(
                "app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient("last entry hata do")
            )
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit"})
            ws.receive_json()  # transcript_final
            ws.receive_json()  # saving
            s3 = ws.receive_json()  # saved
            assert s3["action"] == "voided"
            assert s3["balance_paise"] == 0
            ws.receive_json()  # audio_start
            ws.receive_bytes()  # audio
            ws.receive_json()  # audio_end
            ws.receive_json()  # timings


def test_voice_ambiguous_direction_prompts_clarify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.ws_voice.GnaniSTTClient", lambda **kw: FakeSTTClient("Ramesh ko 200 diya")
    )
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice") as ws:
            ws.receive_json()  # disclosure
            ws.send_json({"type": "start"})
            ws.receive_json()
            ws.send_bytes(b"\x00" * 3200)
            ws.send_json({"type": "commit"})
            ws.receive_json()  # transcript_final
            clarify_msg = ws.receive_json()
            assert clarify_msg["type"] == "clarify"
            assert (
                "udhaar" in clarify_msg["question"].lower()
                or "jama" in clarify_msg["question"].lower()
            )
