"""WebSocket voice session pipeline (§4.3, §4.4, §5)."""

import time
import uuid
from typing import Any

from app.api.ledger_api import DEFAULT_SHOP_ID
from app.dialogue.session import SessionState, VoiceSession
from app.dialogue.templates import (
    render_confirmation_speech,
    render_correction_speech,
    render_undo_speech,
)
from app.nlu.rules_parser import parse_utterance
from app.storage.db import get_session_factory
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.voice import stt_client
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

GnaniSTTClient = stt_client.GnaniSTTClient
router = APIRouter()


def _get_stt_client_instance() -> Any:
    """Return an STT client instance respecting test monkeypatches (§3.2)."""
    if GnaniSTTClient is not stt_client.SarvamSTTClient:
        return GnaniSTTClient()
    if stt_client.GnaniSTTClient is not stt_client.SarvamSTTClient:
        return stt_client.GnaniSTTClient()
    return stt_client.SarvamSTTClient()


# Fixed pre-synthesized audio cache placeholder (PCM16 silence / beep 200ms)
_PRECACHED_AUDIO_CHUNKS: dict[str, bytes] = {
    "default": b"\x00" * 3200,
}


async def _run_tts(ws: WebSocket, text: str, language: str = "hi-IN") -> None:
    """Stream TTS binary frames framed by audio_start and audio_end JSON (§4.4 item 9)."""
    # 1. audio_start control message
    await ws.send_json(
        {
            "type": "audio_start",
            "format": "pcm16",
            "sample_rate": 22050,
            "text": text,
        }
    )

    # 2. Stream binary audio chunks
    audio_chunk = _PRECACHED_AUDIO_CHUNKS.get("default", b"\x00" * 3200)
    await ws.send_bytes(audio_chunk)

    # 3. audio_end control message
    await ws.send_json(
        {
            "type": "audio_end",
        }
    )


@router.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket) -> None:
    """Bi-directional streaming voice WebSocket session (§4.4)."""
    await websocket.accept()

    # Turn 0: AI disclosure turn (§4.4, §6 Phase 4)
    await websocket.send_json(
        {
            "type": "disclosure",
            "text": "Voice Khata AI Munim. Bolna shuru kijiye.",
            "t_ms": 0.0,
        }
    )

    session = VoiceSession(shop_id=DEFAULT_SHOP_ID)
    stt_client_inst = _get_stt_client_instance()
    stt_session = stt_client_inst.session(language=session.language)
    enc_service = EncryptionService()
    session_factory = get_session_factory()

    # Pre-provision default shop if needed
    async with session_factory() as db_sess:
        ledger = LedgerService(db_sess, encryption_service=enc_service)
        await ledger.ensure_shop_exists(session.shop_id)

    try:
        while True:
            raw_msg = await websocket.receive()
            if raw_msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in raw_msg and raw_msg["bytes"] is not None:
                audio_bytes: bytes = raw_msg["bytes"]
                session.append_audio(audio_bytes)
                if session.state == SessionState.LISTENING:
                    await stt_session.send_audio(audio_bytes)
                continue

            msg: dict[str, Any] = {}
            if "text" in raw_msg and raw_msg["text"] is not None:
                import json

                try:
                    msg = json.loads(raw_msg["text"])
                except Exception:
                    msg = {}

            msg_type = msg.get("type", "")

            if msg_type == "start":
                lang = msg.get("language", "hi-IN")
                session.start_utterance(language=lang)
                stt_client_inst = _get_stt_client_instance()
                stt_session = stt_client_inst.session(language=lang)
                await websocket.send_json(
                    {
                        "type": "listening",
                        "t_ms": 0.0,
                    }
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "cancel":
                session.state = SessionState.IDLE
                await websocket.send_json({"type": "cancelled", "t_ms": 0.0})

            elif msg_type == "commit":
                t0 = session.commit_utterance()

                # 1. Finalize STT
                t_stt0 = time.perf_counter()
                transcript = await stt_session.finish()
                stt_ms = (time.perf_counter() - t_stt0) * 1000.0
                t_since_commit = (time.perf_counter() - t0) * 1000.0

                await websocket.send_json(
                    {
                        "type": "transcript_final",
                        "text": transcript,
                        "t_ms": round(t_since_commit, 2),
                    }
                )

                # 2. Fast-path deterministic NLU parse
                t_parse0 = time.perf_counter()
                session_ctx = {
                    "current_customer_name": session.current_customer_name,
                    "last_event_id": session.last_event_id,
                }
                parse_res = parse_utterance(transcript, session_context=session_ctx)
                parse_ms = (time.perf_counter() - t_parse0) * 1000.0

                # 3. Route according to parse action
                action = parse_res.action

                if action == "clarification_needed":
                    q = parse_res.question or "Kripya dobara bolein."
                    await websocket.send_json(
                        {
                            "type": "clarify",
                            "question": q,
                            "options": parse_res.options,
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )
                    t_tts0 = time.perf_counter()
                    await _run_tts(websocket, q, session.language)
                    tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0
                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": 0.0,
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

                elif action in ("undo", "void"):
                    await websocket.send_json(
                        {
                            "type": "saving",
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )
                    t_commit0 = time.perf_counter()
                    commit_ms = 0.0
                    async with session_factory() as db_sess:
                        ledger = LedgerService(db_sess, encryption_service=enc_service)
                        if session.last_event_id:
                            void_rec = await ledger.void_event(
                                session.shop_id, session.last_event_id
                            )
                            await db_sess.commit()
                            commit_ms = (time.perf_counter() - t_commit0) * 1000.0
                            await websocket.send_json(
                                {
                                    "type": "saved",
                                    "action": "voided",
                                    "event_id": void_rec.event_id,
                                    "balance_paise": void_rec.new_balance_paise,
                                    "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                                }
                            )
                            session.update_context(last_event_id=None)
                            speech = render_undo_speech(session.language)
                            t_tts0 = time.perf_counter()
                            await _run_tts(websocket, speech, session.language)
                            tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0
                        else:
                            await websocket.send_json(
                                {
                                    "type": "clarify",
                                    "question": "Hataane ke liye koi entry nahi mili.",
                                    "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                                }
                            )
                            tts_first_ms = 0.0

                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": round(commit_ms, 2),
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

                elif action == "correct":
                    await websocket.send_json(
                        {
                            "type": "saving",
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )
                    t_commit0 = time.perf_counter()
                    commit_ms = 0.0
                    async with session_factory() as db_sess:
                        ledger = LedgerService(db_sess, encryption_service=enc_service)
                        if session.last_event_id and parse_res.events:
                            new_amt = parse_res.events[0].amount_paise
                            amend_rec = await ledger.amend_event(
                                session.shop_id, session.last_event_id, new_amt
                            )
                            await db_sess.commit()
                            commit_ms = (time.perf_counter() - t_commit0) * 1000.0
                            await websocket.send_json(
                                {
                                    "type": "saved",
                                    "action": "amended",
                                    "event_id": amend_rec.event_id,
                                    "new_amount_paise": new_amt,
                                    "balance_paise": amend_rec.new_balance_paise,
                                    "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                                }
                            )
                            session.update_context(
                                last_event_id=amend_rec.event_id,
                                last_amount_paise=new_amt,
                            )
                            speech = render_correction_speech(
                                session.current_customer_name or "Customer",
                                new_amt,
                                amend_rec.new_balance_paise,
                                session.language,
                            )
                            t_tts0 = time.perf_counter()
                            await _run_tts(websocket, speech, session.language)
                            tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0
                        else:
                            await websocket.send_json(
                                {
                                    "type": "clarify",
                                    "question": "Sudharne ke liye koi entry nahi mili.",
                                    "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                                }
                            )
                            tts_first_ms = 0.0

                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": round(commit_ms, 2),
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

                elif action == "query":
                    cust_name = parse_res.customer_name or session.current_customer_name
                    if cust_name:
                        async with session_factory() as db_sess:
                            ledger = LedgerService(db_sess, encryption_service=enc_service)
                            cust_id, _ = await ledger.get_or_create_customer(
                                session.shop_id, cust_name
                            )
                            bal = await ledger.get_cached_balance(session.shop_id, cust_id)
                            bal_num = bal // 100
                            ans = f"{cust_name} ka balance {bal_num} rupaye hai."
                            await websocket.send_json(
                                {
                                    "type": "saved",
                                    "query_answer": ans,
                                    "customer_name": cust_name,
                                    "balance_paise": bal,
                                    "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                                }
                            )
                            t_tts0 = time.perf_counter()
                            await _run_tts(websocket, ans, session.language)
                            tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0
                    else:
                        ans = "Kiska balance dekhna hai?"
                        await websocket.send_json(
                            {
                                "type": "clarify",
                                "question": ans,
                                "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                            }
                        )
                        t_tts0 = time.perf_counter()
                        await _run_tts(websocket, ans, session.language)
                        tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0

                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": 0.0,
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

                elif action == "record":
                    await websocket.send_json(
                        {
                            "type": "saving",
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )
                    t_commit0 = time.perf_counter()
                    saved_events_list: list[dict[str, Any]] = []
                    last_rec = None

                    async with session_factory() as db_sess:
                        ledger = LedgerService(db_sess, encryption_service=enc_service)
                        for idx, evt in enumerate(parse_res.events):
                            base_idem = msg.get("idempotency_key") or f"voice_{uuid.uuid4()}"
                            idem = f"{base_idem}_{idx}" if len(parse_res.events) > 1 else base_idem
                            rec = await ledger.record_event(
                                shop_id=session.shop_id,
                                customer_name=evt.customer_name,
                                amount_paise=evt.amount_paise,
                                direction=evt.direction,
                                occurred_on=evt.occurred_on,
                                idempotency_key=idem,
                                note=evt.note,
                            )
                            saved_events_list.append(
                                {
                                    "event_id": rec.event_id,
                                    "amount_paise": rec.amount_paise,
                                    "direction": rec.direction.value,
                                    "is_duplicate": rec.is_duplicate,
                                }
                            )
                            last_rec = rec
                        await db_sess.commit()

                    commit_ms = (time.perf_counter() - t_commit0) * 1000.0
                    new_bal = last_rec.new_balance_paise if last_rec else 0
                    cust_name = (
                        last_rec.customer_name
                        if last_rec
                        else (parse_res.customer_name or "Customer")
                    )

                    # Fast-path on-screen card: emit saved immediately (§4.3 item 7)
                    await websocket.send_json(
                        {
                            "type": "saved",
                            "events": saved_events_list,
                            "customer_name": cust_name,
                            "balance_paise": new_bal,
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )

                    session.update_context(
                        customer_id=last_rec.customer_id if last_rec else None,
                        customer_name=cust_name,
                        last_event_id=last_rec.event_id if last_rec else None,
                        last_amount_paise=last_rec.amount_paise if last_rec else None,
                        action="record",
                    )

                    # Dynamic or cached TTS confirmation
                    first_evt = parse_res.events[0]
                    speech = render_confirmation_speech(
                        cust_name,
                        first_evt.amount_paise,
                        first_evt.direction,
                        new_bal,
                        session.language,
                    )
                    t_tts0 = time.perf_counter()
                    await _run_tts(websocket, speech, session.language)
                    tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0

                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": round(commit_ms, 2),
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

                else:
                    # Unknown / unparsed utterance -> ask shopkeeper to clarify
                    q = "Kripya dobara bolein."
                    await websocket.send_json(
                        {
                            "type": "clarify",
                            "question": q,
                            "t_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                        }
                    )
                    t_tts0 = time.perf_counter()
                    await _run_tts(websocket, q, session.language)
                    tts_first_ms = (time.perf_counter() - t_tts0) * 1000.0
                    server_total_ms = (time.perf_counter() - t0) * 1000.0
                    await websocket.send_json(
                        {
                            "type": "timings",
                            "stt_ms": round(stt_ms, 2),
                            "parse_ms": round(parse_ms, 2),
                            "commit_ms": 0.0,
                            "tts_first_ms": round(tts_first_ms, 2),
                            "server_total_ms": round(server_total_ms, 2),
                            "t_ms": round(server_total_ms, 2),
                        }
                    )

    except WebSocketDisconnect:
        session.state = SessionState.IDLE
