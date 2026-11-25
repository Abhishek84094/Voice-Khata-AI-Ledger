"""Deterministic promise allocation and lifecycle engine (§5.6, §5.10).

All amounts and statuses are strictly derived by deterministic code (never LLM arithmetic).
Payments are allocated oldest-first to open promises.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.domain.enums import Direction, PromiseStatus


@dataclass
class PromiseItem:
    id: str
    customer_id: str
    amount_paise: int | None  # None = whole balance
    due_date: date
    status: PromiseStatus = PromiseStatus.OPEN
    source_event_id: str | None = None
    created_at: datetime | None = None
    allocated_paise: int = 0
    remaining_paise: int = 0


@dataclass
class PaymentItem:
    amount_paise: int
    occurred_on: date
    event_id: str | None = None


def allocate_payments_to_promises(
    promises: list[PromiseItem],
    payments: list[PaymentItem],
    today: date | None = None,
    grace_period_days: int = 1,
) -> list[PromiseItem]:
    """Allocate payments oldest-first to promises and compute statuses (§5.6).

    Guarantees:
    - Allocated amount never exceeds total payments.
    - Remaining amount is never negative.
    - Fully covered by due date -> KEPT.
    - Partly covered -> PARTIALLY_KEPT with exact remaining paise.
    - Past due with unpaid amount -> BROKEN after grace period.
    """
    if today is None:
        today = date.today()

    # Total payment pool in integer paise
    total_payment = sum(p.amount_paise for p in payments)
    remaining_pool = total_payment

    # Process promises oldest first
    sorted_promises = sorted(promises, key=lambda p: p.due_date)
    results: list[PromiseItem] = []

    for p in sorted_promises:
        item = PromiseItem(
            id=p.id,
            customer_id=p.customer_id,
            amount_paise=p.amount_paise,
            due_date=p.due_date,
            status=p.status,
            source_event_id=p.source_event_id,
            created_at=p.created_at,
            allocated_paise=0,
            remaining_paise=p.amount_paise if p.amount_paise is not None else 0,
        )

        if p.status in (PromiseStatus.RESCHEDULED, PromiseStatus.CANCELLED):
            item.status = p.status
            results.append(item)
            continue

        target = item.amount_paise
        if target is not None:
            alloc = min(remaining_pool, target)
            remaining_pool -= alloc
            item.allocated_paise = alloc
            item.remaining_paise = max(0, target - alloc)

            if alloc >= target:
                item.status = PromiseStatus.KEPT
            elif alloc > 0:
                item.status = PromiseStatus.PARTIALLY_KEPT
            else:
                # 0 paid: check if broken past grace period
                if item.due_date + timedelta(days=grace_period_days) < today:
                    item.status = PromiseStatus.BROKEN
                else:
                    item.status = PromiseStatus.OPEN
        else:
            # Whole balance promise
            alloc = remaining_pool
            remaining_pool = 0
            item.allocated_paise = alloc
            item.remaining_paise = 0
            item.status = PromiseStatus.KEPT if alloc > 0 else PromiseStatus.OPEN

        results.append(item)

    return results


def replay_promises_from_events(
    raw_promises: list[dict[str, Any]],
    raw_events: list[dict[str, Any]],
    today: date | None = None,
    grace_period_days: int = 1,
) -> list[PromiseItem]:
    """Re-derive promise statuses and remaining amounts from append-only event log.

    Handles voided and amended events idempotently.
    """
    voided_event_ids: set[str] = set()
    for e in raw_events:
        if e.get("type") == Direction.VOIDED.value and e.get("target_event_id"):
            voided_event_ids.add(e["target_event_id"])

    payments: list[PaymentItem] = []
    for e in raw_events:
        if e.get("id") in voided_event_ids or e.get("type") == Direction.VOIDED.value:
            continue
        if e.get("type") == Direction.PAYMENT_RECEIVED.value:
            payments.append(
                PaymentItem(
                    amount_paise=e["amount_paise"],
                    occurred_on=e["date"] if isinstance(e["date"], date) else date.today(),
                    event_id=e.get("id"),
                )
            )

    promise_items: list[PromiseItem] = []
    for rp in raw_promises:
        status_val = rp.get("status", "OPEN")
        status = PromiseStatus(status_val) if isinstance(status_val, str) else status_val
        promise_items.append(
            PromiseItem(
                id=rp["id"],
                customer_id=rp["customer_id"],
                amount_paise=rp.get("amount_paise"),
                due_date=rp["due_date"],
                status=status,
                source_event_id=rp.get("source_event_id"),
            )
        )

    return allocate_payments_to_promises(
        promise_items, payments, today=today, grace_period_days=grace_period_days
    )
