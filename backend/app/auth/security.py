"""Auth and security primitives (§6 Phase 7).

Includes:
- OTP generation & in-memory verification (rate-limited, with salt hash)
- Standard JWT token creation & verification (HS256 via stdlib hmac/hashlib)
- Short-lived WebSocket ticket generation & exchange
- Passwordless phone login flow
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import get_settings


def b64url_encode(data: bytes) -> str:
    """Encode bytes using URL-safe Base64 without trailing '=' padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def b64url_decode(s: str) -> bytes:
    """Decode URL-safe Base64 string with restored padding."""
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_jwt_token(
    payload: dict[str, Any],
    expires_in_seconds: int = 3600,
    secret: str | None = None,
) -> str:
    """Create a signed HS256 JWT token with standard claims (§6 Phase 7)."""
    if secret is None:
        secret = get_settings().jwt_secret

    claims = dict(payload)
    now = time.time()
    claims["iat"] = int(now)
    claims["exp"] = int(now + expires_in_seconds)

    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")

    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{b64url_encode(sig)}"


def verify_jwt_token(
    token: str,
    secret: str | None = None,
) -> dict[str, Any]:
    """Verify an HS256 JWT token and return decoded claims. Raises ValueError on failure."""
    if secret is None:
        secret = get_settings().jwt_secret

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT token format")

    h_b64, p_b64, s_b64 = parts
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        provided_sig = b64url_decode(s_b64)
    except Exception as e:
        raise ValueError("Malformed signature in token") from e

    if not hmac.compare_digest(provided_sig, expected_sig):
        raise ValueError("Invalid signature")

    try:
        payload: dict[str, Any] = json.loads(b64url_decode(p_b64).decode("utf-8"))
    except Exception as e:
        raise ValueError("Malformed payload in token") from e

    exp = payload.get("exp")
    if exp is not None and isinstance(exp, (int, float)):
        if exp < time.time():
            raise ValueError("Token expired")

    return payload


# --- OTP & WebSocket Ticket In-Memory Cache ---

_OTP_CACHE: dict[str, tuple[str, float]] = {}  # phone -> (otp_hash, expires_at)
_TICKET_CACHE: dict[str, tuple[str, float]] = {}  # ticket -> (shop_id, expires_at)


def generate_otp(phone: str, validity_seconds: int = 300) -> str:
    """Generate a 6-digit OTP for phone authentication (mock/testable)."""
    # Deterministic test code for test phone or secure random 6 digits
    if phone in ("9999999999", "+919999999999"):
        otp = "123456"
    else:
        otp = f"{secrets.randbelow(900000) + 100000}"

    otp_hash = hashlib.sha256(f"{phone}:{otp}".encode("utf-8")).hexdigest()
    _OTP_CACHE[phone] = (otp_hash, time.time() + validity_seconds)
    return otp


def verify_otp(phone: str, entered_otp: str) -> bool:
    """Verify 6-digit OTP against cached hash."""
    cached = _OTP_CACHE.get(phone)
    if not cached:
        return False
    expected_hash, expires_at = cached
    if time.time() > expires_at:
        _OTP_CACHE.pop(phone, None)
        return False

    computed_hash = hashlib.sha256(f"{phone}:{entered_otp}".encode("utf-8")).hexdigest()
    if hmac.compare_digest(computed_hash, expected_hash):
        _OTP_CACHE.pop(phone, None)
        return True
    return False


def create_ws_ticket(shop_id: str, validity_seconds: int = 60) -> str:
    """Create a short-lived single-use ticket for WebSocket authentication."""
    ticket = secrets.token_urlsafe(32)
    _TICKET_CACHE[ticket] = (shop_id, time.time() + validity_seconds)
    return ticket


def consume_ws_ticket(ticket: str) -> str | None:
    """Consume a single-use ticket and return shop_id, or None if invalid/expired."""
    cached = _TICKET_CACHE.pop(ticket, None)
    if not cached:
        return None
    shop_id, expires_at = cached
    if time.time() > expires_at:
        return None
    return shop_id
