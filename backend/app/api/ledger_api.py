"""REST endpoints for inspecting the ledger and customer balances (§3.2, §5.1)."""

from typing import Any

from app.storage.db import get_db_session as get_session
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.storage.models import Customer, LedgerEvent
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["ledger"])

# Default shop ID for development and test harnesses
DEFAULT_SHOP_ID = "00000000-0000-0000-0000-000000000001"


def get_encryption_service() -> EncryptionService:
    return EncryptionService()


@router.get("/ledger")
async def get_ledger_events(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Return all non-voided ledger events with decrypted fields."""
    query = (
        select(LedgerEvent, Customer.display_name_enc)
        .join(Customer, LedgerEvent.customer_id == Customer.id)
        .where(LedgerEvent.shop_id == DEFAULT_SHOP_ID)
        .order_by(LedgerEvent.recorded_at.desc())
    )
    res = await session.execute(query)
    rows = res.all()

    items: list[dict[str, Any]] = []
    for evt, cust_name_enc in rows:
        try:
            amount_paise = enc_service.decrypt_int(evt.amount_paise_enc)
        except Exception:
            amount_paise = 0
        try:
            note = enc_service.decrypt_text(evt.note_enc) if evt.note_enc else None
        except Exception:
            note = None
        try:
            cust_name = enc_service.decrypt_text(cust_name_enc)
        except Exception:
            cust_name = "[Customer]"
        items.append(
            {
                "id": evt.id,
                "customer_id": evt.customer_id,
                "customer_name": cust_name,
                "type": evt.type.value if hasattr(evt.type, "value") else str(evt.type),
                "amount_paise": amount_paise,
                "amount_rupees": amount_paise / 100.0,
                "occurred_on": evt.occurred_on.isoformat(),
                "recorded_at": evt.recorded_at.isoformat(),
                "note": note,
                "target_event_id": evt.target_event_id,
            }
        )
    return items


@router.get("/customers")
async def get_customers(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Return all customers with their decrypted names and current cached balances."""
    service = LedgerService(session, encryption_service=enc_service)
    customers = await service.get_shop_customers(DEFAULT_SHOP_ID)

    items: list[dict[str, Any]] = []
    for c in customers:
        try:
            name = enc_service.decrypt_text(c.display_name_enc)
        except Exception:
            name = "[Customer]"
        bal = await service.get_cached_balance(DEFAULT_SHOP_ID, c.id)
        items.append(
            {
                "id": c.id,
                "display_name": name,
                "search_key": c.search_key,
                "balance_paise": bal,
                "balance_rupees": bal / 100.0,
            }
        )
    return items


@router.get("/export")
async def export_data(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Export all decrypted ledger data for the shop (§5.1)."""
    service = LedgerService(session, encryption_service=enc_service)
    return await service.export_all_data(DEFAULT_SHOP_ID)


@router.delete("/data")
async def delete_all_data(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Purge all shop records (§5.1)."""
    service = LedgerService(session, encryption_service=enc_service)
    await service.delete_all_data(DEFAULT_SHOP_ID)
    return {"status": "purged", "shop_id": DEFAULT_SHOP_ID}
