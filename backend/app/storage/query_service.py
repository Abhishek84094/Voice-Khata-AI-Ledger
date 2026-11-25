"""Query service for business summaries, debtors, dues, and recent activity (§5.1, §6 Phase 6).

Executes fast indexed SQL queries scoped to shop_id.
"""

from __future__ import annotations

from datetime import date

from app.domain.enums import Direction, PromiseStatus
from app.domain.queries import (
    DebtorItem,
    DuePromiseItem,
    PeriodSummary,
    RecentEntryItem,
)
from app.storage.encryption import EncryptionService, get_encryption_service
from app.storage.ledger_service import LedgerService
from app.storage.models import Customer, CustomerBalance, LedgerEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class QueryService:
    def __init__(
        self,
        session: AsyncSession,
        encryption_service: EncryptionService | None = None,
    ) -> None:
        self.session = session
        self.enc = encryption_service or get_encryption_service()
        self.ledger = LedgerService(session, encryption_service=self.enc)

    async def get_period_summary(
        self,
        shop_id: str,
        start_date: date,
        end_date: date,
        period: str = "custom",
    ) -> PeriodSummary:
        """Calculate total credit and payments over a date range (§6 Phase 6)."""
        stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.shop_id == shop_id,
                LedgerEvent.occurred_on >= start_date,
                LedgerEvent.occurred_on <= end_date,
            )
            .order_by(LedgerEvent.recorded_at.asc())
        )
        res = await self.session.execute(stmt)
        events = list(res.scalars().all())

        # Exclude voided events
        voided_ids: set[str] = {
            e.target_event_id
            for e in events
            if e.type == Direction.VOIDED.value and e.target_event_id
        }

        credit_paise = 0
        payment_paise = 0

        for e in events:
            if e.id in voided_ids or e.type == Direction.VOIDED.value:
                continue
            try:
                amt = self.enc.decrypt_int(e.amount_paise_enc)
            except Exception:
                amt = 0

            if e.type == Direction.CREDIT_GIVEN.value:
                credit_paise += amt
            elif e.type == Direction.PAYMENT_RECEIVED.value:
                payment_paise += amt

        return PeriodSummary(
            credit_paise=credit_paise,
            payment_paise=payment_paise,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_top_debtors(
        self,
        shop_id: str,
        limit: int = 5,
    ) -> list[DebtorItem]:
        """Fetch customers with highest positive balance (§5.1, §6 Phase 6)."""
        stmt = (
            select(CustomerBalance, Customer.display_name_enc)
            .join(Customer, CustomerBalance.customer_id == Customer.id)
            .where(
                CustomerBalance.shop_id == shop_id,
                CustomerBalance.balance_paise > 0,
            )
            .order_by(CustomerBalance.balance_paise.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        rows = res.all()

        out: list[DebtorItem] = []
        for bal_rec, name_enc in rows:
            try:
                name = self.enc.decrypt_text(name_enc)
            except Exception:
                name = "[Customer]"
            out.append(
                DebtorItem(
                    customer_id=bal_rec.customer_id,
                    customer_name=name,
                    balance_paise=bal_rec.balance_paise,
                )
            )
        return out

    async def get_due_promises(
        self,
        shop_id: str,
        target_date: date | None = None,
    ) -> list[DuePromiseItem]:
        """Fetch promises due on a specific target date (default today)."""
        if target_date is None:
            target_date = date.today()

        stmt = select(Customer).where(Customer.shop_id == shop_id)
        cust_res = await self.session.execute(stmt)
        customers = {
            c.id: self._safe_decrypt_text(c.display_name_enc) for c in cust_res.scalars().all()
        }

        out: list[DuePromiseItem] = []
        for cust_id, cust_name in customers.items():
            proms = await self.ledger.get_customer_promises(shop_id, cust_id, today=target_date)
            for p in proms:
                if (
                    p.due_date == target_date
                    and p.status in (PromiseStatus.OPEN, PromiseStatus.PARTIALLY_KEPT)
                    and p.remaining_paise > 0
                ):
                    out.append(
                        DuePromiseItem(
                            promise_id=p.id,
                            customer_id=cust_id,
                            customer_name=cust_name,
                            remaining_paise=p.remaining_paise,
                            due_date=p.due_date,
                            status=p.status.value,
                        )
                    )
        return out

    async def get_overdue_promises(
        self,
        shop_id: str,
        today: date | None = None,
        grace_period_days: int = 1,
    ) -> list[DuePromiseItem]:
        """Fetch promises past due date with an unpaid remaining amount (§5.6)."""
        if today is None:
            today = date.today()

        stmt = select(Customer).where(Customer.shop_id == shop_id)
        cust_res = await self.session.execute(stmt)
        customers = {
            c.id: self._safe_decrypt_text(c.display_name_enc) for c in cust_res.scalars().all()
        }

        out: list[DuePromiseItem] = []
        for cust_id, cust_name in customers.items():
            proms = await self.ledger.get_customer_promises(shop_id, cust_id, today=today)
            for p in proms:
                if p.status == PromiseStatus.BROKEN or (
                    p.due_date < today and p.remaining_paise > 0
                ):
                    out.append(
                        DuePromiseItem(
                            promise_id=p.id,
                            customer_id=cust_id,
                            customer_name=cust_name,
                            remaining_paise=p.remaining_paise,
                            due_date=p.due_date,
                            status=p.status.value,
                        )
                    )
        return out

    async def get_recent_entries(
        self,
        shop_id: str,
        limit: int = 5,
    ) -> list[RecentEntryItem]:
        """Fetch recent non-voided ledger events with decrypted customer names."""
        stmt = (
            select(LedgerEvent, Customer.display_name_enc)
            .join(Customer, LedgerEvent.customer_id == Customer.id)
            .where(
                LedgerEvent.shop_id == shop_id,
                LedgerEvent.type != Direction.VOIDED.value,
            )
            .order_by(LedgerEvent.recorded_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        rows = res.all()

        out: list[RecentEntryItem] = []
        for evt, name_enc in rows:
            name = self._safe_decrypt_text(name_enc)
            try:
                amt = self.enc.decrypt_int(evt.amount_paise_enc)
            except Exception:
                amt = 0
            note = self._safe_decrypt_text(evt.note_enc) if evt.note_enc else None
            out.append(
                RecentEntryItem(
                    event_id=evt.id,
                    customer_name=name,
                    amount_paise=amt,
                    direction=evt.type,
                    occurred_on=evt.occurred_on,
                    note=note,
                )
            )
        return out

    def _safe_decrypt_text(self, token: str) -> str:
        try:
            return self.enc.decrypt_text(token)
        except Exception:
            return "[Customer]"
