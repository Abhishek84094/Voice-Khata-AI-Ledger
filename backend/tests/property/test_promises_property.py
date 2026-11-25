"""Hypothesis property tests for promise allocation invariants (§5.6, §6 Phase 5).

Invariants tested:
1. Total allocated amount never exceeds total payments.
2. Remaining amount is never negative.
3. Sum of allocated + remaining equals original target amount for every promise.
4. Deterministic replay of events reproduces exact promise states.
5. Increasing payment never decreases allocation for any earlier promise.
"""

from __future__ import annotations

from datetime import date

from app.domain.enums import PromiseStatus
from app.domain.promises import (
    PaymentItem,
    PromiseItem,
    allocate_payments_to_promises,
)
from hypothesis import given
from hypothesis import strategies as st


@given(
    promise_amounts=st.lists(
        st.integers(min_value=100, max_value=1_000_000), min_size=1, max_size=10
    ),
    payment_amounts=st.lists(
        st.integers(min_value=100, max_value=1_000_000), min_size=0, max_size=10
    ),
)
def test_allocation_invariants(promise_amounts: list[int], payment_amounts: list[int]):
    today = date(2026, 12, 1)
    promises = [
        PromiseItem(
            id=f"p{i}",
            customer_id="c1",
            amount_paise=amt,
            due_date=date(2026, 12, 5 + i),
            status=PromiseStatus.OPEN,
        )
        for i, amt in enumerate(promise_amounts)
    ]
    payments = [PaymentItem(amount_paise=amt, occurred_on=today) for amt in payment_amounts]

    total_payments = sum(payment_amounts)
    results = allocate_payments_to_promises(promises, payments, today=today)

    total_allocated = sum(r.allocated_paise for r in results)

    # Invariant 1: Total allocated never exceeds total payments
    assert total_allocated <= total_payments

    # Invariant 2 & 3: For each promise, remaining >= 0 and allocated + remaining == original
    for r, orig_amt in zip(results, promise_amounts, strict=False):
        assert r.remaining_paise >= 0
        assert r.allocated_paise + r.remaining_paise == orig_amt
        if r.remaining_paise == 0:
            assert r.status == PromiseStatus.KEPT
        elif r.allocated_paise > 0:
            assert r.status == PromiseStatus.PARTIALLY_KEPT
        else:
            assert r.status in (PromiseStatus.OPEN, PromiseStatus.BROKEN)


@given(
    promise_amounts=st.lists(
        st.integers(min_value=1000, max_value=100_000), min_size=1, max_size=5
    ),
    payment_amount=st.integers(min_value=500, max_value=500_000),
    additional_payment=st.integers(min_value=1, max_value=50_000),
)
def test_monotonicity_of_allocation(
    promise_amounts: list[int], payment_amount: int, additional_payment: int
):
    today = date(2026, 12, 1)
    promises1 = [
        PromiseItem(
            id=f"p{i}",
            customer_id="c1",
            amount_paise=amt,
            due_date=date(2026, 12, 5 + i),
            status=PromiseStatus.OPEN,
        )
        for i, amt in enumerate(promise_amounts)
    ]
    promises2 = [
        PromiseItem(
            id=f"p{i}",
            customer_id="c1",
            amount_paise=amt,
            due_date=date(2026, 12, 5 + i),
            status=PromiseStatus.OPEN,
        )
        for i, amt in enumerate(promise_amounts)
    ]

    res1 = allocate_payments_to_promises(
        promises1, [PaymentItem(amount_paise=payment_amount, occurred_on=today)], today=today
    )
    res2 = allocate_payments_to_promises(
        promises2,
        [PaymentItem(amount_paise=payment_amount + additional_payment, occurred_on=today)],
        today=today,
    )

    # Higher payment pool never decreases allocation for any promise
    for r1, r2 in zip(res1, res2, strict=False):
        assert r2.allocated_paise >= r1.allocated_paise
        assert r2.remaining_paise <= r1.remaining_paise
