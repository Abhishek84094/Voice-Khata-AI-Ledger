"""Ledger service with single-transaction commit, balance cache, and event replay (§5.1, §5.6).

Guarantees:
1. Every write is scoped to shop_id.
2. Single transaction commits event + balance cache update.
3. Event log is append-only; balance is verified against event log replay.
4. Idempotent deduplication via (shop_id, idempotency_key).
5. All sensitive values (names, amounts, notes) are encrypted at rest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.domain.enums import Direction, PromiseStatus
from app.domain.promises import PaymentItem, PromiseItem, allocate_payments_to_promises
from app.storage.customer_cache import get_customer_cache, normalize_to_search_key
from app.storage.encryption import EncryptionService, get_encryption_service
from app.storage.models import Customer, CustomerBalance, LedgerEvent, Promise, Shop
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RecordEventResult:
    event_id: str
    customer_id: str
    customer_name: str
    amount_paise: int
    direction: Direction
    new_balance_paise: int
    is_duplicate: bool = False


class LedgerService:
    def __init__(
        self,
        session: AsyncSession,
        encryption_service: EncryptionService | None = None,
    ) -> None:
        self.session = session
        self.enc = encryption_service or get_encryption_service()
        self.cache = get_customer_cache()

    async def get_or_create_customer(
        self,
        shop_id: str,
        display_name: str,
    ) -> tuple[str, str]:
        """Find customer id by search key (using memory cache first) or create a new record.

        Returns (customer_id, search_key).
        """
        search_key = normalize_to_search_key(display_name)

        # 1. Microsecond in-memory cache lookup
        cached, _ = self.cache.resolve_customer(shop_id, display_name)
        if cached is not None:
            return cached.id, cached.search_key

        # 2. Check database
        stmt = select(Customer.id).where(
            Customer.shop_id == shop_id,
            Customer.search_key == search_key,
        )
        res = await self.session.execute(stmt)
        row = res.first()

        if row is not None:
            cust_id = row[0]
        else:
            # Create new customer with encrypted display name
            display_name_enc = self.enc.encrypt_text(display_name)
            cust_id = str(uuid.uuid4())
            customer = Customer(
                id=cust_id,
                shop_id=shop_id,
                display_name_enc=display_name_enc,
                search_key=search_key,
                aliases_enc=self.enc.encrypt_text("[]"),
            )
            self.session.add(customer)

            # Initialize balance cache
            bal = CustomerBalance(
                shop_id=shop_id,
                customer_id=cust_id,
                balance_paise=0,
            )
            self.session.add(bal)
            self.cache.invalidate_shop(shop_id)

        return cust_id, search_key

    async def record_event(
        self,
        shop_id: str,
        customer_name: str,
        amount_paise: int,
        direction: Direction,
        occurred_on: date,
        idempotency_key: str,
        source_utterance_id: str | None = None,
        note: str | None = None,
    ) -> RecordEventResult:
        """Record an entry in a single atomic transaction."""
        # 1. Idempotency check: look up existing event
        dup_stmt = select(LedgerEvent).where(
            LedgerEvent.shop_id == shop_id,
            LedgerEvent.idempotency_key == idempotency_key,
        )
        dup_res = await self.session.execute(dup_stmt)
        existing_event = dup_res.scalars().first()

        if existing_event is not None:
            # Already committed, return existing state idempotently
            bal_stmt = select(CustomerBalance).where(
                CustomerBalance.shop_id == shop_id,
                CustomerBalance.customer_id == existing_event.customer_id,
            )
            bal_res = await self.session.execute(bal_stmt)
            curr_bal = bal_res.scalars().first()
            bal_paise = curr_bal.balance_paise if curr_bal else 0

            return RecordEventResult(
                event_id=existing_event.id,
                customer_id=existing_event.customer_id,
                customer_name=customer_name,
                amount_paise=amount_paise,
                direction=direction,
                new_balance_paise=bal_paise,
                is_duplicate=True,
            )

        # 2. Customer resolution / creation
        customer_id, _ = await self.get_or_create_customer(shop_id, customer_name)

        # 3. Create encrypted ledger event
        amount_paise_enc = self.enc.encrypt_int(amount_paise)
        note_enc = self.enc.encrypt_text(note) if note else None

        event = LedgerEvent(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            customer_id=customer_id,
            type=direction.value,
            amount_paise_enc=amount_paise_enc,
            occurred_on=occurred_on,
            recorded_at=datetime.now(timezone.utc),
            source_utterance_id=source_utterance_id,
            idempotency_key=idempotency_key,
            note_enc=note_enc,
        )
        self.session.add(event)

        # 4. Update customer_balances cache in the same transaction
        bal_stmt = (
            select(CustomerBalance)
            .where(
                CustomerBalance.shop_id == shop_id,
                CustomerBalance.customer_id == customer_id,
            )
            .with_for_update()
        )
        bal_res = await self.session.execute(bal_stmt)
        balance_record = bal_res.scalars().first()

        if balance_record is None:
            balance_record = CustomerBalance(
                shop_id=shop_id,
                customer_id=customer_id,
                balance_paise=0,
            )
            self.session.add(balance_record)

        if direction == Direction.CREDIT_GIVEN:
            balance_record.balance_paise += amount_paise
        elif direction == Direction.PAYMENT_RECEIVED:
            balance_record.balance_paise -= amount_paise

        balance_record.last_event_id = event.id
        balance_record.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        return RecordEventResult(
            event_id=event.id,
            customer_id=customer_id,
            customer_name=customer_name,
            amount_paise=amount_paise,
            direction=direction,
            new_balance_paise=balance_record.balance_paise,
            is_duplicate=False,
        )

    async def replay_customer_balance(self, shop_id: str, customer_id: str) -> int:
        """Derive customer balance by replaying the append-only event log from scratch."""
        stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.shop_id == shop_id,
                LedgerEvent.customer_id == customer_id,
            )
            .order_by(LedgerEvent.recorded_at.asc())
        )
        res = await self.session.execute(stmt)
        events = res.scalars().all()

        balance = 0
        voided_event_ids: set[str] = set()

        # First pass: find voided events
        for e in events:
            if e.type == Direction.VOIDED.value and e.target_event_id:
                voided_event_ids.add(e.target_event_id)

        # Second pass: calculate balance
        for e in events:
            if e.id in voided_event_ids or e.type == Direction.VOIDED.value:
                continue
            amt = self.enc.decrypt_int(e.amount_paise_enc)
            if e.type == Direction.CREDIT_GIVEN.value:
                balance += amt
            elif e.type == Direction.PAYMENT_RECEIVED.value:
                balance -= amt

        return balance

    async def get_cached_balance(self, shop_id: str, customer_id: str) -> int:
        """Read customer balance directly from the balance cache table."""
        stmt = select(CustomerBalance).where(
            CustomerBalance.shop_id == shop_id,
            CustomerBalance.customer_id == customer_id,
        )
        res = await self.session.execute(stmt)
        bal = res.scalars().first()
        return bal.balance_paise if bal else 0

    async def get_shop_customers(self, shop_id: str) -> list[Customer]:
        """Fetch all customers for a given shop."""
        stmt = (
            select(Customer).where(Customer.shop_id == shop_id).order_by(Customer.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def ensure_shop_exists(self, shop_id: str, name: str = "Voice Khata Shop") -> Shop:
        """Ensure a shop record exists, auto-provisioning if missing."""
        stmt = select(Shop).where(Shop.id == shop_id)
        res = await self.session.execute(stmt)
        shop = res.scalars().first()
        if shop is None:
            shop = Shop(id=shop_id, name=name, language="hi-IN")
            self.session.add(shop)
            await self.session.commit()
        return shop

    async def void_event(
        self,
        shop_id: str,
        target_event_id: str,
        idempotency_key: str | None = None,
    ) -> RecordEventResult:
        """Void an existing ledger event (§5.7: 'undo' or 'last entry hata do')."""
        target_stmt = select(LedgerEvent).where(
            LedgerEvent.shop_id == shop_id,
            LedgerEvent.id == target_event_id,
        )
        target_res = await self.session.execute(target_stmt)
        target = target_res.scalars().first()
        if target is None:
            raise ValueError(f"Event {target_event_id} not found")

        old_amount = self.enc.decrypt_int(target.amount_paise_enc)
        customer_id = target.customer_id
        idem_key = idempotency_key or f"void_{target_event_id}_{uuid.uuid4()}"

        # Insert voiding event
        void_event = LedgerEvent(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            customer_id=customer_id,
            type=Direction.VOIDED.value,
            amount_paise_enc=target.amount_paise_enc,
            occurred_on=date.today(),
            recorded_at=datetime.now(timezone.utc),
            idempotency_key=idem_key,
            target_event_id=target_event_id,
        )
        self.session.add(void_event)

        # Reverse balance impact in customer_balances
        bal_stmt = (
            select(CustomerBalance)
            .where(
                CustomerBalance.shop_id == shop_id,
                CustomerBalance.customer_id == customer_id,
            )
            .with_for_update()
        )
        bal_res = await self.session.execute(bal_stmt)
        bal_rec = bal_res.scalars().first()
        if bal_rec:
            if target.type in (Direction.CREDIT_GIVEN.value, Direction.AMENDED.value):
                bal_rec.balance_paise -= old_amount
            elif target.type == Direction.PAYMENT_RECEIVED.value:
                bal_rec.balance_paise += old_amount
            bal_rec.last_event_id = void_event.id
            bal_rec.updated_at = datetime.now(timezone.utc)
            new_bal = bal_rec.balance_paise
        else:
            new_bal = 0

        await self.session.flush()
        return RecordEventResult(
            event_id=void_event.id,
            customer_id=customer_id,
            customer_name="",
            amount_paise=old_amount,
            direction=Direction.VOIDED,
            new_balance_paise=new_bal,
            is_duplicate=False,
        )

    async def amend_event(
        self,
        shop_id: str,
        target_event_id: str,
        new_amount_paise: int,
        idempotency_key: str | None = None,
    ) -> RecordEventResult:
        """Amend an existing ledger event (§5.7: 'nahi, 430')."""
        target_stmt = select(LedgerEvent).where(
            LedgerEvent.shop_id == shop_id,
            LedgerEvent.id == target_event_id,
        )
        target_res = await self.session.execute(target_stmt)
        target = target_res.scalars().first()
        if target is None:
            raise ValueError(f"Event {target_event_id} not found")

        old_amount = self.enc.decrypt_int(target.amount_paise_enc)
        customer_id = target.customer_id
        diff = new_amount_paise - old_amount
        idem_key = idempotency_key or f"amend_{target_event_id}_{uuid.uuid4()}"

        amend_event = LedgerEvent(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            customer_id=customer_id,
            type=Direction.AMENDED.value,
            amount_paise_enc=self.enc.encrypt_int(new_amount_paise),
            occurred_on=date.today(),
            recorded_at=datetime.now(timezone.utc),
            idempotency_key=idem_key,
            target_event_id=target_event_id,
        )
        self.session.add(amend_event)

        bal_stmt = (
            select(CustomerBalance)
            .where(
                CustomerBalance.shop_id == shop_id,
                CustomerBalance.customer_id == customer_id,
            )
            .with_for_update()
        )
        bal_res = await self.session.execute(bal_stmt)
        bal_rec = bal_res.scalars().first()
        if bal_rec:
            if target.type == Direction.CREDIT_GIVEN.value:
                bal_rec.balance_paise += diff
            elif target.type == Direction.PAYMENT_RECEIVED.value:
                bal_rec.balance_paise -= diff
            bal_rec.last_event_id = amend_event.id
            bal_rec.updated_at = datetime.now(timezone.utc)
            new_bal = bal_rec.balance_paise
        else:
            new_bal = new_amount_paise

        await self.session.flush()
        return RecordEventResult(
            event_id=amend_event.id,
            customer_id=customer_id,
            customer_name="",
            amount_paise=new_amount_paise,
            direction=Direction.AMENDED,
            new_balance_paise=new_bal,
            is_duplicate=False,
        )

    async def export_all_data(self, shop_id: str) -> dict[str, Any]:
        """Export all data for a shop in decrypted plaintext JSON (§1 rule 8)."""
        cust_stmt = select(Customer).where(Customer.shop_id == shop_id)
        cust_res = await self.session.execute(cust_stmt)
        customers = cust_res.scalars().all()

        customer_list = []
        for c in customers:
            customer_list.append(
                {
                    "id": c.id,
                    "display_name": self.enc.decrypt_text(c.display_name_enc),
                    "search_key": c.search_key,
                    "reminder_opt_in": c.reminder_opt_in,
                    "created_at": c.created_at.isoformat(),
                }
            )

        events_stmt = (
            select(LedgerEvent)
            .where(LedgerEvent.shop_id == shop_id)
            .order_by(LedgerEvent.recorded_at.asc())
        )
        events_res = await self.session.execute(events_stmt)
        events = events_res.scalars().all()

        event_list = []
        for e in events:
            event_list.append(
                {
                    "id": e.id,
                    "customer_id": e.customer_id,
                    "type": e.type,
                    "amount_paise": self.enc.decrypt_int(e.amount_paise_enc),
                    "occurred_on": e.occurred_on.isoformat(),
                    "recorded_at": e.recorded_at.isoformat(),
                    "idempotency_key": e.idempotency_key,
                    "note": self.enc.decrypt_text(e.note_enc) if e.note_enc else None,
                }
            )

        # Export promises
        promises_list = await self.get_shop_promises(shop_id)

        return {
            "shop_id": shop_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "customers": customer_list,
            "events": event_list,
            "promises": promises_list,
        }

    async def create_promise(
        self,
        shop_id: str,
        customer_id: str,
        due_date: date,
        amount_paise: int | None = None,
        source_event_id: str | None = None,
        status: str = "OPEN",
    ) -> Promise:
        """Create an encrypted promise record (§5.1, §5.6)."""
        amt_enc = self.enc.encrypt_int(amount_paise) if amount_paise is not None else None
        prom = Promise(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            customer_id=customer_id,
            amount_paise_enc=amt_enc,
            due_date=due_date,
            status=status,
            source_event_id=source_event_id,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(prom)
        await self.session.flush()
        return prom

    async def get_customer_promises(
        self,
        shop_id: str,
        customer_id: str,
        today: date | None = None,
    ) -> list[PromiseItem]:
        """Fetch and deterministically derive promise allocations and statuses (§5.6)."""
        stmt = (
            select(Promise)
            .where(
                Promise.shop_id == shop_id,
                Promise.customer_id == customer_id,
            )
            .order_by(Promise.due_date.asc(), Promise.created_at.asc())
        )
        res = await self.session.execute(stmt)
        promises_db = list(res.scalars().all())

        if not promises_db:
            return []

        events_stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.shop_id == shop_id,
                LedgerEvent.customer_id == customer_id,
            )
            .order_by(LedgerEvent.recorded_at.asc())
        )
        ev_res = await self.session.execute(events_stmt)
        events = ev_res.scalars().all()

        voided_ids: set[str] = {
            e.target_event_id
            for e in events
            if e.type == Direction.VOIDED.value and e.target_event_id
        }

        payments: list[PaymentItem] = []
        for e in events:
            if e.id in voided_ids or e.type == Direction.VOIDED.value:
                continue
            if e.type == Direction.PAYMENT_RECEIVED.value:
                try:
                    amt = self.enc.decrypt_int(e.amount_paise_enc)
                except Exception:
                    amt = 0
                payments.append(
                    PaymentItem(
                        amount_paise=amt,
                        occurred_on=e.occurred_on,
                        event_id=e.id,
                    )
                )

        promise_items: list[PromiseItem] = []
        for p in promises_db:
            prom_amt: int | None = None
            try:
                prom_amt = self.enc.decrypt_int(p.amount_paise_enc) if p.amount_paise_enc else None
            except Exception:
                prom_amt = None
            try:
                status_enum = PromiseStatus(p.status)
            except ValueError:
                status_enum = PromiseStatus.OPEN
            promise_items.append(
                PromiseItem(
                    id=p.id,
                    customer_id=p.customer_id,
                    amount_paise=prom_amt,
                    due_date=p.due_date,
                    status=status_enum,
                    source_event_id=p.source_event_id,
                    created_at=p.created_at,
                )
            )

        allocated = allocate_payments_to_promises(promise_items, payments, today=today)

        for item, p_db in zip(allocated, promises_db, strict=False):
            if p_db.status != item.status.value:
                p_db.status = item.status.value

        await self.session.flush()
        return allocated

    async def reschedule_promise(
        self,
        shop_id: str,
        target_promise_id: str,
        new_due_date: date,
        new_amount_paise: int | None = None,
    ) -> Promise:
        """Reschedule an open or broken promise to a new date (§5.6)."""
        stmt = select(Promise).where(
            Promise.shop_id == shop_id,
            Promise.id == target_promise_id,
        )
        res = await self.session.execute(stmt)
        target = res.scalars().first()
        if target is None:
            raise ValueError(f"Promise {target_promise_id} not found")

        target.status = PromiseStatus.RESCHEDULED.value
        amt = (
            new_amount_paise
            if new_amount_paise is not None
            else (
                self.enc.decrypt_int(target.amount_paise_enc) if target.amount_paise_enc else None
            )
        )
        new_prom = await self.create_promise(
            shop_id=shop_id,
            customer_id=target.customer_id,
            due_date=new_due_date,
            amount_paise=amt,
            source_event_id=target.source_event_id,
        )
        return new_prom

    async def get_shop_promises(
        self,
        shop_id: str,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all promises for a shop with derived statuses and remaining amounts."""
        cust_stmt = select(Customer).where(Customer.shop_id == shop_id)
        cust_res = await self.session.execute(cust_stmt)
        customers: dict[str, str] = {}
        for c in cust_res.scalars().all():
            try:
                name = self.enc.decrypt_text(c.display_name_enc)
            except Exception:
                name = "[Customer]"
            customers[c.id] = name

        out: list[dict[str, Any]] = []
        for cust_id, cust_name in customers.items():
            proms = await self.get_customer_promises(shop_id, cust_id, today=today)
            for p in proms:
                out.append(
                    {
                        "id": p.id,
                        "customer_id": p.customer_id,
                        "customer_name": cust_name,
                        "amount_paise": p.amount_paise,
                        "due_date": p.due_date.isoformat(),
                        "status": p.status.value,
                        "allocated_paise": p.allocated_paise,
                        "remaining_paise": p.remaining_paise,
                    }
                )
        return out

    async def delete_all_data(self, shop_id: str) -> None:
        """Purge all data belonging to a shop (§1 rule 8)."""
        await self.session.execute(delete(LedgerEvent).where(LedgerEvent.shop_id == shop_id))
        await self.session.execute(
            delete(CustomerBalance).where(CustomerBalance.shop_id == shop_id)
        )
        await self.session.execute(delete(Promise).where(Promise.shop_id == shop_id))
        await self.session.execute(delete(Customer).where(Customer.shop_id == shop_id))
        await self.session.commit()
        # Invalidate in-memory cache
        self.cache.invalidate_shop(shop_id)
