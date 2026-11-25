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

from app.domain.enums import Direction
from app.storage.customer_cache import get_customer_cache, normalize_to_search_key
from app.storage.encryption import EncryptionService, get_encryption_service
from app.storage.models import Customer, CustomerBalance, LedgerEvent, Promise
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

        return {
            "shop_id": shop_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "customers": customer_list,
            "events": event_list,
        }

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
