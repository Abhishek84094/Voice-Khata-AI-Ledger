"""Unit and integration tests for QueryService and Reporting REST endpoints."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.api.ledger_api import DEFAULT_SHOP_ID
from app.dialogue.templates import (
    render_customer_balance_speech,
    render_due_today_speech,
    render_overdue_speech,
    render_period_summary_speech,
    render_top_debtors_speech,
)
from app.domain.enums import Direction
from app.domain.queries import PeriodSummary
from app.main import create_app
from app.storage.db import get_session_factory
from app.storage.encryption import get_encryption_service
from app.storage.ledger_service import LedgerService
from app.storage.query_service import QueryService
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_query_service_comprehensive_methods() -> None:
    session_factory = get_session_factory()
    enc_service = get_encryption_service()

    async with session_factory() as sess:
        ledger = LedgerService(sess, encryption_service=enc_service)
        qs = QueryService(sess, encryption_service=enc_service)

        shop_id = DEFAULT_SHOP_ID
        await ledger.ensure_shop_exists(shop_id, "Test Shop")
        cust_id, _ = await ledger.get_or_create_customer(shop_id, "TestQS Customer")

        today = date.today()
        # Record credit
        await ledger.record_event(
            shop_id=shop_id,
            customer_name="TestQS Customer",
            amount_paise=500000,
            direction=Direction.CREDIT_GIVEN,
            occurred_on=today,
            idempotency_key=f"idemp-1-{today.isoformat()}",
        )
        # Record payment
        await ledger.record_event(
            shop_id=shop_id,
            customer_name="TestQS Customer",
            amount_paise=150000,
            direction=Direction.PAYMENT_RECEIVED,
            occurred_on=today,
            idempotency_key=f"idemp-2-{today.isoformat()}",
        )

        # Create promise due today
        await ledger.create_promise(
            shop_id=shop_id,
            customer_id=cust_id,
            due_date=today,
            amount_paise=200000,
        )

        # Create overdue promise with amount larger than payment so it remains unpaid
        await ledger.create_promise(
            shop_id=shop_id,
            customer_id=cust_id,
            due_date=today - timedelta(days=5),
            amount_paise=400000,
        )

        # Test period summaries
        summ_today = await qs.get_period_summary(shop_id, today, today, period="today")
        assert summ_today.credit_paise == 500000
        assert summ_today.payment_paise == 150000
        assert summ_today.net_paise == 350000

        summ_week = await qs.get_period_summary(
            shop_id, today - timedelta(days=7), today, period="this_week"
        )
        assert summ_week.credit_paise == 500000

        summ_month = await qs.get_period_summary(
            shop_id, today.replace(day=1), today, period="this_month"
        )
        assert summ_month.credit_paise == 500000

        # Test top debtors
        debtors = await qs.get_top_debtors(shop_id, limit=5)
        assert len(debtors) >= 1
        assert any(d.customer_name == "TestQS Customer" for d in debtors)

        # Test due promises
        dues = await qs.get_due_promises(shop_id, target_date=today)
        assert len(dues) >= 1
        assert any(d.customer_name == "TestQS Customer" for d in dues)

        # Test overdue promises
        overdues = await qs.get_overdue_promises(shop_id, today=today)
        assert len(overdues) >= 1

        # Test recent entries
        recent = await qs.get_recent_entries(shop_id, limit=5)
        assert len(recent) >= 2


def test_reporting_rest_endpoints() -> None:
    app = create_app()
    with TestClient(app) as client:
        # Seed an event
        client.post(
            "/api/ledger",
            json={
                "customer_name": "ReportTestCust",
                "amount_paise": 300000,
                "direction": "CREDIT_GIVEN",
            },
        )

        res_sum_today = client.get("/api/reports/summary?period=today")
        assert res_sum_today.status_code == 200
        data_today = res_sum_today.json()
        assert "credit_paise" in data_today
        assert "payment_paise" in data_today

        res_sum_week = client.get("/api/reports/summary?period=this_week")
        assert res_sum_week.status_code == 200

        res_sum_month = client.get("/api/reports/summary?period=this_month")
        assert res_sum_month.status_code == 200

        res_debtors = client.get("/api/reports/top-debtors?limit=5")
        assert res_debtors.status_code == 200
        assert isinstance(res_debtors.json(), list)

        res_due = client.get("/api/reports/due-today")
        assert res_due.status_code == 200
        assert isinstance(res_due.json(), list)

        res_overdue = client.get("/api/reports/overdue")
        assert res_overdue.status_code == 200
        assert isinstance(res_overdue.json(), list)


def test_spoken_templates_edge_cases() -> None:
    # English spoken templates
    s_en = render_customer_balance_speech("Ramesh", 50000, language="en-IN")
    assert "Ramesh" in s_en
    assert "₹500" in s_en

    s_adv_en = render_customer_balance_speech("Suresh", -20000, language="en-IN")
    assert "advance" in s_adv_en

    s_zero_en = render_customer_balance_speech("Anita", 0, language="en-IN")
    assert "settled" in s_zero_en

    summ = PeriodSummary(credit_paise=100000, payment_paise=40000, period="today")
    s_sum_en = render_period_summary_speech(summ, language="en-IN")
    assert "₹1000" in s_sum_en

    s_top_empty = render_top_debtors_speech([], language="hi-IN")
    assert "nahi hai" in s_top_empty

    s_due_empty = render_due_today_speech([], language="hi-IN")
    assert "due nahi hai" in s_due_empty

    s_overdue_empty = render_overdue_speech([], language="hi-IN")
    assert "nahi hai" in s_overdue_empty
