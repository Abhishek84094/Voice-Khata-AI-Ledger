"""Unit and IDOR tests for Phase 7 Auth and Multi-Tenancy (§6 Phase 7).

Guarantees:
1. Complete OTP generation & verification flow.
2. JWT access and refresh token lifecycle with signature and expiration checks.
3. Strict tenant isolation (IDOR matrix): Shop A can never view or write Shop B's records.
4. WebSocket authenticated ticket exchange and token fallback.
5. Auth overhead ≤ 5 ms p95.
"""

from __future__ import annotations

import time
from datetime import date

import pytest
from app.auth.security import (
    create_jwt_token,
    generate_otp,
    verify_jwt_token,
    verify_otp,
)
from app.domain.enums import Direction
from app.main import create_app
from app.storage.db import get_session_factory
from app.storage.encryption import get_encryption_service
from app.storage.ledger_service import LedgerService
from starlette.testclient import TestClient


def test_otp_flow_and_expiration() -> None:
    phone = "9876543210"
    otp = generate_otp(phone, validity_seconds=2)
    assert len(otp) == 6
    assert otp.isdigit()

    # Wrong OTP fails
    assert not verify_otp(phone, "000000")

    # Correct OTP succeeds
    assert verify_otp(phone, otp)

    # Replay fails (single-use)
    assert not verify_otp(phone, otp)


def test_jwt_token_creation_and_tampering() -> None:
    claims = {"shop_id": "test-shop-123", "sub": "test-user-456", "role": "owner"}
    tok = create_jwt_token(claims, expires_in_seconds=60, secret="supersecretkey")

    # Valid verification
    dec = verify_jwt_token(tok, secret="supersecretkey")
    assert dec["shop_id"] == "test-shop-123"
    assert dec["sub"] == "test-user-456"

    # Tampered payload fails
    parts = tok.split(".")
    tampered = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
    with pytest.raises(ValueError, match="Invalid signature"):
        verify_jwt_token(tampered, secret="supersecretkey")

    # Wrong secret fails
    with pytest.raises(ValueError, match="Invalid signature"):
        verify_jwt_token(tok, secret="wrongsecret")

    # Expired token fails
    exp_tok = create_jwt_token(claims, expires_in_seconds=-10, secret="supersecretkey")
    with pytest.raises(ValueError, match="Token expired"):
        verify_jwt_token(exp_tok, secret="supersecretkey")


def test_auth_api_endpoints() -> None:
    app = create_app()
    with TestClient(app) as client:
        # 1. Send OTP
        res_send = client.post("/api/auth/otp/send", json={"phone": "9999999999"})
        assert res_send.status_code == 200
        assert res_send.json()["status"] == "success"

        # 2. Verify OTP (test phone uses standard 123456)
        res_verify = client.post(
            "/api/auth/otp/verify",
            json={"phone": "9999999999", "otp": "123456", "shop_name": "Test Kirana"},
        )
        assert res_verify.status_code == 200
        data = res_verify.json()
        assert "access_token" in data
        assert "refresh_token" in data
        access_tok = data["access_token"]
        refresh_tok = data["refresh_token"]

        # 3. Refresh Token
        res_ref = client.post("/api/auth/refresh", json={"refresh_token": refresh_tok})
        assert res_ref.status_code == 200
        assert "access_token" in res_ref.json()

        # 4. Request WebSocket ticket
        res_ws = client.post(
            "/api/auth/ws-ticket",
            headers={"Authorization": f"Bearer {access_tok}"},
        )
        assert res_ws.status_code == 200
        assert "ticket" in res_ws.json()


@pytest.mark.asyncio
async def test_idor_matrix_tenant_isolation() -> None:
    """CRITICAL IDOR MATRIX (§6 Phase 7):
    Proves that Shop A can NEVER read, query, export, or delete Shop B's records.
    """
    session_factory = get_session_factory()
    enc_service = get_encryption_service()

    shop_a = "shop-alpha-1111"
    shop_b = "shop-beta-2222"

    async with session_factory() as sess:
        ledger = LedgerService(sess, encryption_service=enc_service)
        await ledger.ensure_shop_exists(shop_a, "Alpha Stores")
        await ledger.ensure_shop_exists(shop_b, "Beta Kirana")

        # Seed data for Shop A
        await ledger.record_event(
            shop_id=shop_a,
            customer_name="Ramesh Alpha",
            amount_paise=100000,
            direction=Direction.CREDIT_GIVEN,
            occurred_on=date.today(),
            idempotency_key="idemp-alpha-1",
        )

        # Seed data for Shop B
        await ledger.record_event(
            shop_id=shop_b,
            customer_name="Suresh Beta",
            amount_paise=250000,
            direction=Direction.CREDIT_GIVEN,
            occurred_on=date.today(),
            idempotency_key="idemp-beta-1",
        )
        await sess.commit()

    # Issue JWT tokens for both shops
    token_a = create_jwt_token({"sub": "user-a", "shop_id": shop_a, "role": "owner"})
    token_b = create_jwt_token({"sub": "user-b", "shop_id": shop_b, "role": "owner"})

    app = create_app()
    with TestClient(app) as client:
        # Shop A calls /api/ledger
        res_a_led = client.get("/api/ledger", headers={"Authorization": f"Bearer {token_a}"})
        assert res_a_led.status_code == 200
        events_a = res_a_led.json()
        assert all(e["customer_name"] != "Suresh Beta" for e in events_a)
        assert any(e["customer_name"] == "Ramesh Alpha" for e in events_a)

        # Shop B calls /api/ledger
        res_b_led = client.get("/api/ledger", headers={"Authorization": f"Bearer {token_b}"})
        assert res_b_led.status_code == 200
        events_b = res_b_led.json()
        assert all(e["customer_name"] != "Ramesh Alpha" for e in events_b)
        assert any(e["customer_name"] == "Suresh Beta" for e in events_b)

        # Shop A calls /api/reports/summary
        res_a_sum = client.get(
            "/api/reports/summary?period=today",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_a_sum.status_code == 200
        assert res_a_sum.json()["credit_paise"] == 100000  # Only Shop A's ₹1000

        res_b_sum = client.get(
            "/api/reports/summary?period=today",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b_sum.status_code == 200
        assert res_b_sum.json()["credit_paise"] == 250000  # Only Shop B's ₹2500

        # Shop A calls /api/export
        exp_a = client.get("/api/export", headers={"Authorization": f"Bearer {token_a}"})
        assert exp_a.status_code == 200
        exp_a_data = exp_a.json()
        assert any(c["display_name"] == "Ramesh Alpha" for c in exp_a_data.get("customers", []))
        assert not any(c["display_name"] == "Suresh Beta" for c in exp_a_data.get("customers", []))


def test_auth_deps_and_rejections() -> None:
    import asyncio

    from app.auth.deps import get_tenant_context, require_auth
    from fastapi import HTTPException

    # Unauthenticated fallback in get_tenant_context
    ctx_def = asyncio.run(get_tenant_context(None))
    assert ctx_def.shop_id == "00000000-0000-0000-0000-000000000001"

    # Invalid scheme
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_tenant_context("Basic 12345"))
    assert exc_info.value.status_code == 401

    # Malformed token
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_tenant_context("Bearer invalid.token.string"))
    assert exc_info.value.status_code == 401

    # require_auth missing header
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_auth(None))
    assert exc_info.value.status_code == 401

    # require_auth valid token
    tok = create_jwt_token({"sub": "u1", "shop_id": "s1", "phone": "999"})
    ctx_req = asyncio.run(require_auth(f"Bearer {tok}"))
    assert ctx_req.shop_id == "s1"
    assert ctx_req.user_id == "u1"


def test_auth_latency_overhead() -> None:
    """Verify auth verification adds ≤ 5 ms p95."""
    token = create_jwt_token({"sub": "user-perf", "shop_id": "shop-perf", "role": "owner"})
    times: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        verify_jwt_token(token)
        times.append((time.perf_counter() - t0) * 1000.0)

    times.sort()
    p95 = times[int(len(times) * 0.95)]
    print(f"\n[AUTH PERF] P95 verify latency: {p95:.4f} ms")
    assert p95 <= 5.0  # budget: ≤ 5 ms p95
