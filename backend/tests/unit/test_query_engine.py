"""Unit tests for deterministic query engine and spoken answers (§4.3 item 11, §6 Phase 6).

Guarantees:
1. Rules-based query parser recognizes all standard shopkeeper questions without an LLM.
2. Period summaries, customer balance, top debtors, due today, overdue, and last N entries.
3. Natural per-language spoken templates in Hinglish and English.
"""

from __future__ import annotations

from datetime import date

from app.dialogue.templates import (
    render_customer_balance_speech,
    render_due_today_speech,
    render_overdue_speech,
    render_period_summary_speech,
    render_top_debtors_speech,
)
from app.domain.queries import (
    DebtorItem,
    DuePromiseItem,
    PeriodSummary,
    QueryType,
    parse_query,
)


def test_parse_customer_balance_query():
    q1 = parse_query("Ramesh ka kitna baaki hai?")
    assert q1.query_type == QueryType.CUSTOMER_BALANCE
    assert q1.customer_name == "Ramesh"

    q2 = parse_query("Suresh ka total hisaab batao")
    assert q2.query_type == QueryType.CUSTOMER_BALANCE
    assert q2.customer_name == "Suresh"

    q3 = parse_query("how much does Priya owe?")
    assert q3.query_type == QueryType.CUSTOMER_BALANCE
    assert q3.customer_name == "Priya"


def test_parse_period_summary_query():
    # Today
    q_today = parse_query("aaj kitna udhaar gaya?")
    assert q_today.query_type == QueryType.PERIOD_SUMMARY
    assert q_today.period == "today"
    assert q_today.metric == "credit"

    q_today_jam = parse_query("aaj kitna jama hua?")
    assert q_today_jam.query_type == QueryType.PERIOD_SUMMARY
    assert q_today_jam.period == "today"
    assert q_today_jam.metric == "payment"

    # This week
    q_week = parse_query("is hafte kitna udhaar gaya?")
    assert q_week.query_type == QueryType.PERIOD_SUMMARY
    assert q_week.period == "this_week"

    # This month
    q_month = parse_query("is mahine kitna jama hua?")
    assert q_month.query_type == QueryType.PERIOD_SUMMARY
    assert q_month.period == "this_month"


def test_parse_top_debtors_query():
    q1 = parse_query("sabse zyada udhaar kiska hai?")
    assert q1.query_type == QueryType.TOP_DEBTORS

    q2 = parse_query("top debtors")
    assert q2.query_type == QueryType.TOP_DEBTORS


def test_parse_due_and_overdue_queries():
    q_due = parse_query("aaj kiska payment aana hai?")
    assert q_due.query_type == QueryType.DUE_TODAY

    q_due_en = parse_query("who has payments due today?")
    assert q_due_en.query_type == QueryType.DUE_TODAY

    q_overdue = parse_query("kiska payment overdue hai?")
    assert q_overdue.query_type == QueryType.OVERDUE

    q_overdue_en = parse_query("overdue promises")
    assert q_overdue_en.query_type == QueryType.OVERDUE


def test_parse_last_entries_query():
    q = parse_query("aakhiri entries dikhao")
    assert q.query_type == QueryType.LAST_ENTRIES


def test_spoken_customer_balance_templates():
    # Positive (credit owed)
    s_pos = render_customer_balance_speech("Ramesh", 34000, "hi-IN")
    assert "Ramesh" in s_pos
    assert "340" in s_pos
    assert "baaki" in s_pos.lower()

    # Negative (advance)
    s_adv = render_customer_balance_speech("Suresh", -20000, "hi-IN")
    assert "Suresh" in s_adv
    assert "200" in s_adv
    assert "advance" in s_adv.lower()

    # Zero (all settled)
    s_zero = render_customer_balance_speech("Anita", 0, "hi-IN")
    assert "Anita" in s_zero
    assert "barabar" in s_zero.lower() or "settled" in s_zero.lower()


def test_spoken_period_summary_templates():
    summary = PeriodSummary(
        credit_paise=150000,  # ₹1500
        payment_paise=80000,  # ₹800
        period="today",
    )
    s = render_period_summary_speech(summary, language="hi-IN")
    assert "1500" in s
    assert "800" in s
    assert "udhaar" in s.lower()
    assert "jama" in s.lower()


def test_spoken_top_debtors_templates():
    debtors = [
        DebtorItem(customer_id="c1", customer_name="Ramesh", balance_paise=250000),
        DebtorItem(customer_id="c2", customer_name="Suresh", balance_paise=180000),
    ]
    s = render_top_debtors_speech(debtors, language="hi-IN")
    assert "Ramesh" in s
    assert "2500" in s
    assert "Suresh" in s
    assert "1800" in s


def test_spoken_due_and_overdue_templates():
    dues = [
        DuePromiseItem(
            promise_id="p1",
            customer_id="c1",
            customer_name="Ramesh",
            remaining_paise=120000,
            due_date=date(2026, 11, 20),
        )
    ]
    s_due = render_due_today_speech(dues, language="hi-IN")
    assert "Ramesh" in s_due
    assert "1200" in s_due

    s_overdue = render_overdue_speech(dues, language="hi-IN")
    assert "Ramesh" in s_overdue
    assert "1200" in s_overdue
    assert "overdue" in s_overdue.lower() or "baaki" in s_overdue.lower()
