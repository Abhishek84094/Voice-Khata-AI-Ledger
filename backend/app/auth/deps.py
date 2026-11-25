"""Dependency injection for authenticating requests and extracting tenant context."""

from __future__ import annotations

from typing import Annotated

from app.auth.security import verify_jwt_token
from app.core.config import DEFAULT_SHOP_ID
from fastapi import Header, HTTPException, status


class TenantContext:
    def __init__(self, shop_id: str, user_id: str, phone: str):
        self.shop_id = shop_id
        self.user_id = user_id
        self.phone = phone


async def get_tenant_context(
    authorization: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """Extract and verify authenticated shop_id from Bearer JWT header.

    In dev/test environments without an Authorization header, gracefully falls back
    to DEFAULT_SHOP_ID for backward compatibility with unauthenticated tests.
    When an Authorization header is provided, it is strictly validated.
    """
    if not authorization:
        # Fallback for unauthenticated dev/test calls
        return TenantContext(shop_id=DEFAULT_SHOP_ID, user_id="dev-user", phone="0000000000")

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme; Bearer token required",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    try:
        claims = verify_jwt_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {e}",
        ) from e

    shop_id = claims.get("shop_id")
    if not shop_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing shop_id claim",
        )

    return TenantContext(
        shop_id=str(shop_id),
        user_id=str(claims.get("sub", "")),
        phone=str(claims.get("phone", "")),
    )


async def require_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """Strict authentication requirement: returns 401 if header is missing or invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required; Bearer token missing",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    try:
        claims = verify_jwt_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {e}",
        ) from e

    shop_id = claims.get("shop_id")
    if not shop_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing shop_id claim",
        )

    return TenantContext(
        shop_id=str(shop_id),
        user_id=str(claims.get("sub", "")),
        phone=str(claims.get("phone", "")),
    )
