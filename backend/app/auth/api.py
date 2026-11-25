"""Auth REST API endpoints (§6 Phase 7).

Endpoints:
- POST /api/auth/otp/send: Request OTP for phone
- POST /api/auth/otp/verify: Verify OTP, issue access & refresh JWT tokens
- POST /api/auth/refresh: Exchange refresh token for new access token
- POST /api/auth/ws-ticket: Exchange valid access token for short-lived WS ticket
"""

from __future__ import annotations

import uuid
from typing import Any

from app.auth.security import (
    create_jwt_token,
    create_ws_ticket,
    generate_otp,
    verify_jwt_token,
    verify_otp,
)
from app.storage.db import get_db_session as get_session
from app.storage.encryption import get_encryption_service
from app.storage.ledger_service import LedgerService
from app.storage.models import User
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SendOTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    shop_name: str | None = None


class VerifyOTPRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=4, max_length=8)
    shop_name: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    shop_id: str
    user_id: str
    phone: str


@router.post("/otp/send")
async def send_otp(req: SendOTPRequest) -> dict[str, Any]:
    """Send OTP for shopkeeper phone verification."""
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    otp = generate_otp(clean_phone)
    # In real deployment this calls SMS provider; in dev/test return status
    return {
        "status": "success",
        "message": "OTP sent successfully",
        "phone": clean_phone,
        # For dev/test convenience:
        "dev_otp": otp if clean_phone.endswith("9999") else None,
    }


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp_endpoint(
    req: VerifyOTPRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Verify OTP and return JWT access and refresh tokens."""
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    if not verify_otp(clean_phone, req.otp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    enc_service = get_encryption_service()
    ledger = LedgerService(session, encryption_service=enc_service)

    # Check if user already exists with this phone
    stmt = select(User).where(User.phone == clean_phone)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if user is None:
        # Create new shop and user
        shop_id = str(uuid.uuid4())
        shop_name = req.shop_name or f"Shop {clean_phone[-4:]}"
        await ledger.ensure_shop_exists(shop_id, shop_name)

        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            shop_id=shop_id,
            phone=clean_phone,
            role="owner",
            language="hi-IN",
        )
        session.add(user)
        await session.commit()
    else:
        shop_id = user.shop_id
        user_id = user.id

    access_token = create_jwt_token(
        {"sub": user_id, "shop_id": shop_id, "phone": clean_phone, "type": "access"},
        expires_in_seconds=3600,  # 1 hour
    )
    refresh_token = create_jwt_token(
        {"sub": user_id, "shop_id": shop_id, "phone": clean_phone, "type": "refresh"},
        expires_in_seconds=86400 * 30,  # 30 days
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        shop_id=shop_id,
        user_id=user_id,
        phone=clean_phone,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(req: RefreshTokenRequest) -> TokenResponse:
    """Issue a fresh access token given a valid refresh token."""
    try:
        payload = verify_jwt_token(req.refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {e}",
        ) from e

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    shop_id = str(payload["shop_id"])
    user_id = str(payload["sub"])
    phone = str(payload.get("phone", ""))

    new_access_token = create_jwt_token(
        {"sub": user_id, "shop_id": shop_id, "phone": phone, "type": "access"},
        expires_in_seconds=3600,
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=req.refresh_token,
        shop_id=shop_id,
        user_id=user_id,
        phone=phone,
    )


@router.post("/ws-ticket")
async def get_ws_ticket(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Issue a short-lived single-use WebSocket ticket."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer authorization header",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    try:
        payload = verify_jwt_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {e}",
        ) from e

    shop_id = str(payload["shop_id"])
    ticket = create_ws_ticket(shop_id, validity_seconds=60)
    return {"ticket": ticket, "expires_in_seconds": 60}
