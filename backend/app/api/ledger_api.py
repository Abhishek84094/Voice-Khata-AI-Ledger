"""REST endpoints for inspecting the ledger and customer balances (§3.2, §5.1)."""

from typing import Any

from app.storage.db import get_db_session as get_session
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.storage.models import Customer, LedgerEvent
from app.storage.query_service import QueryService
from fastapi import APIRouter, Depends, Query
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


@router.get("/promises")
async def get_promises(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Return all promises with derived allocations and statuses (§5.6, §6 Phase 5)."""
    service = LedgerService(session, encryption_service=enc_service)
    return await service.get_shop_promises(DEFAULT_SHOP_ID)


@router.get("/reports/summary")
async def get_report_summary(
    period: str = Query("today"),
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> dict[str, Any]:
    """Period summary endpoint for dashboard and cross-checking (§6 Phase 6)."""
    from datetime import date, timedelta

    today = date.today()
    start_d = today
    end_d = today

    if period == "this_week":
        start_d = today - timedelta(days=today.weekday())
        end_d = start_d + timedelta(days=6)
    elif period == "this_month":
        start_d = date(today.year, today.month, 1)
        next_m = today.month % 12 + 1
        next_y = today.year if next_m > 1 else today.year + 1
        end_d = date(next_y, next_m, 1) - timedelta(days=1)

    qs = QueryService(session, encryption_service=enc_service)
    summary = await qs.get_period_summary(DEFAULT_SHOP_ID, start_d, end_d, period=period)
    return {
        "period": period,
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "credit_paise": summary.credit_paise,
        "payment_paise": summary.payment_paise,
        "net_paise": summary.net_paise,
        "credit_rupees": summary.credit_paise / 100.0,
        "payment_rupees": summary.payment_paise / 100.0,
        "net_rupees": summary.net_paise / 100.0,
    }


@router.get("/reports/top-debtors")
async def get_top_debtors(
    limit: int = Query(5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Top debtors endpoint for dashboard and voice cross-checking (§6 Phase 6)."""
    qs = QueryService(session, encryption_service=enc_service)
    debtors = await qs.get_top_debtors(DEFAULT_SHOP_ID, limit=limit)
    return [
        {
            "customer_id": d.customer_id,
            "customer_name": d.customer_name,
            "balance_paise": d.balance_paise,
            "balance_rupees": d.balance_paise / 100.0,
        }
        for d in debtors
    ]


@router.get("/reports/due-today")
async def get_due_today(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Promises due today (§6 Phase 6)."""
    qs = QueryService(session, encryption_service=enc_service)
    dues = await qs.get_due_promises(DEFAULT_SHOP_ID)
    return [
        {
            "promise_id": d.promise_id,
            "customer_id": d.customer_id,
            "customer_name": d.customer_name,
            "remaining_paise": d.remaining_paise,
            "remaining_rupees": d.remaining_paise / 100.0,
            "due_date": d.due_date.isoformat(),
            "status": d.status,
        }
        for d in dues
    ]


@router.get("/reports/overdue")
async def get_overdue(
    session: AsyncSession = Depends(get_session),
    enc_service: EncryptionService = Depends(get_encryption_service),
) -> list[dict[str, Any]]:
    """Overdue promises with remaining unpaid amounts (§6 Phase 6)."""
    qs = QueryService(session, encryption_service=enc_service)
    overdues = await qs.get_overdue_promises(DEFAULT_SHOP_ID)
    return [
        {
            "promise_id": d.promise_id,
            "customer_id": d.customer_id,
            "customer_name": d.customer_name,
            "remaining_paise": d.remaining_paise,
            "remaining_rupees": d.remaining_paise / 100.0,
            "due_date": d.due_date.isoformat(),
            "status": d.status,
        }
        for d in overdues
    ]


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
