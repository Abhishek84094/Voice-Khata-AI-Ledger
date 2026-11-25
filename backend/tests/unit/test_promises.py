"""Unit tests for deterministic promise allocation and lifecycle (§5.6, §5.10).

Guarantees:
1. Code computes all numbers and statuses (LLM never does arithmetic).
2. Payments are allocated oldest-first to open promises.
3. Fully paid -> KEPT.
4. Partly paid -> PARTIALLY_KEPT with exact remaining paise.
5. Zero paid and past due + grace period -> BROKEN.
6. Replay from event log reproduces exact state.
"""

from __future__ import annotations

from datetime import date

from app.domain.enums import PromiseStatus
from app.domain.promises import (
    PaymentItem,
    PromiseItem,
    allocate_payments_to_promises,
    replay_promises_from_events,
)


def test_single_promise_full_payment():
    p = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=200000,  # ₹2000
        due_date=date(2026, 12, 10),
        status=PromiseStatus.OPEN,
    )
    payments = [PaymentItem(amount_paise=200000, occurred_on=date(2026, 12, 5))]

    result = allocate_payments_to_promises([p], payments, today=date(2026, 12, 5))
    assert len(result) == 1
    assert result[0].status == PromiseStatus.KEPT
    assert result[0].allocated_paise == 200000
    assert result[0].remaining_paise == 0


def test_single_promise_partial_payment():
    p = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=200000,  # ₹2000
        due_date=date(2026, 12, 10),
        status=PromiseStatus.OPEN,
    )
    payments = [PaymentItem(amount_paise=80000, occurred_on=date(2026, 12, 5))]  # ₹800

    result = allocate_payments_to_promises([p], payments, today=date(2026, 12, 5))
    assert len(result) == 1
    assert result[0].status == PromiseStatus.PARTIALLY_KEPT
    assert result[0].allocated_paise == 80000
    assert result[0].remaining_paise == 120000  # ₹1200 remaining


def test_oldest_first_allocation():
    p1 = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=50000,  # ₹500
        due_date=date(2026, 12, 1),
        status=PromiseStatus.OPEN,
    )
    p2 = PromiseItem(
        id="p2",
        customer_id="c1",
        amount_paise=100000,  # ₹1000
        due_date=date(2026, 12, 5),
        status=PromiseStatus.OPEN,
    )
    payments = [PaymentItem(amount_paise=70000, occurred_on=date(2026, 12, 2))]

    result = allocate_payments_to_promises([p1, p2], payments, today=date(2026, 12, 2))
    assert len(result) == 2
    # p1 gets 50000 -> KEPT
    assert result[0].id == "p1"
    assert result[0].status == PromiseStatus.KEPT
    assert result[0].allocated_paise == 50000
    assert result[0].remaining_paise == 0

    # p2 gets 20000 -> PARTIALLY_KEPT
    assert result[1].id == "p2"
    assert result[1].status == PromiseStatus.PARTIALLY_KEPT
    assert result[1].allocated_paise == 20000
    assert result[1].remaining_paise == 80000


def test_overdue_promise_becomes_broken():
    today = date(2026, 12, 10)
    p = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=100000,
        due_date=date(2026, 12, 5),  # 5 days ago
        status=PromiseStatus.OPEN,
    )
    result = allocate_payments_to_promises([p], [], today=today, grace_period_days=1)
    assert len(result) == 1
    assert result[0].status == PromiseStatus.BROKEN
    assert result[0].remaining_paise == 100000


def test_grace_period_keeps_open():
    today = date(2026, 12, 6)
    p = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=100000,
        due_date=date(2026, 12, 5),  # 1 day ago
        status=PromiseStatus.OPEN,
    )
    # Grace period is 1 day, so on Dec 6 it is within grace period
    result = allocate_payments_to_promises([p], [], today=today, grace_period_days=1)
    assert len(result) == 1
    assert result[0].status == PromiseStatus.OPEN


def test_rescheduled_promise_preserved():
    p1 = PromiseItem(
        id="p1",
        customer_id="c1",
        amount_paise=100000,
        due_date=date(2026, 12, 1),
        status=PromiseStatus.RESCHEDULED,
    )
    p2 = PromiseItem(
        id="p2",
        customer_id="c1",
        amount_paise=100000,
        due_date=date(2026, 12, 10),
        status=PromiseStatus.OPEN,
    )
    payments = [PaymentItem(amount_paise=100000, occurred_on=date(2026, 12, 3))]
    result = allocate_payments_to_promises([p1, p2], payments, today=date(2026, 12, 3))
    assert result[0].id == "p1"
    assert result[0].status == PromiseStatus.RESCHEDULED
    assert result[1].id == "p2"
    assert result[1].status == PromiseStatus.KEPT
    assert result[1].remaining_paise == 0


def test_replay_promises_from_events():
    events = [
        {"type": "CREDIT_GIVEN", "amount_paise": 200000, "date": date(2026, 12, 1)},
        {"type": "PAYMENT_RECEIVED", "amount_paise": 80000, "date": date(2026, 12, 2)},
    ]
    promises = [
        {
            "id": "p1",
            "customer_id": "c1",
            "amount_paise": 200000,
            "due_date": date(2026, 12, 15),
            "status": "OPEN",
        }
    ]
    replayed = replay_promises_from_events(promises, events, today=date(2026, 12, 2))
    assert len(replayed) == 1
    assert replayed[0].status == PromiseStatus.PARTIALLY_KEPT
    assert replayed[0].allocated_paise == 80000
    assert replayed[0].remaining_paise == 120000
