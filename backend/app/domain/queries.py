"""Domain models and rules-based parser for spoken business queries (§4.3 item 11, §6 Phase 6).

All common queries are parsed in microseconds without an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class QueryType(str, Enum):
    CUSTOMER_BALANCE = "CUSTOMER_BALANCE"
    PERIOD_SUMMARY = "PERIOD_SUMMARY"
    TOP_DEBTORS = "TOP_DEBTORS"
    DUE_TODAY = "DUE_TODAY"
    OVERDUE = "OVERDUE"
    LAST_ENTRIES = "LAST_ENTRIES"


@dataclass
class ParsedQuery:
    query_type: QueryType
    customer_name: str | None = None
    period: str = "today"  # today, this_week, this_month, custom
    metric: str = "all"  # all, credit, payment
    limit: int = 5
    start_date: date | None = None
    end_date: date | None = None


@dataclass
class PeriodSummary:
    credit_paise: int
    payment_paise: int
    period: str = "today"
    start_date: date | None = None
    end_date: date | None = None

    @property
    def net_paise(self) -> int:
        return self.credit_paise - self.payment_paise


@dataclass
class DebtorItem:
    customer_id: str
    customer_name: str
    balance_paise: int


@dataclass
class DuePromiseItem:
    promise_id: str
    customer_id: str
    customer_name: str
    remaining_paise: int
    due_date: date
    status: str = "OPEN"


@dataclass
class RecentEntryItem:
    event_id: str
    customer_name: str
    amount_paise: int
    direction: str
    occurred_on: date
    note: str | None = None


def parse_query(text: str) -> ParsedQuery:
    """Parse a shopkeeper query into structured ParsedQuery using microsecond rules."""
    lowered = text.lower().strip()

    # 1. Top Debtors
    if any(
        k in lowered
        for k in (
            "sabse zyada udhaar",
            "sabse jyada udhaar",
            "top debtors",
            "who owes the most",
            "sabse zyada baaki",
            "highest balance",
        )
    ):
        return ParsedQuery(query_type=QueryType.TOP_DEBTORS)

    # 2. Due Today & Overdue
    if any(
        k in lowered
        for k in (
            "overdue",
            "kiska overdue",
            "overdue promises",
            "broken promises",
            "kiska baaki reh gaya",
        )
    ):
        return ParsedQuery(query_type=QueryType.OVERDUE)

    if any(
        k in lowered
        for k in (
            "aaj kiska payment",
            "due today",
            "aaj ke promises",
            "payments due today",
            "aaj kis kis ka aana hai",
        )
    ):
        return ParsedQuery(query_type=QueryType.DUE_TODAY)

    # 3. Last entries
    if any(
        k in lowered
        for k in (
            "aakhiri entries",
            "last entries",
            "recent transactions",
            "pichli entries",
            "recent entries",
            "aakhri entries",
        )
    ):
        m_num = re.search(r"(\d+)", lowered)
        limit = int(m_num.group(1)) if m_num else 5
        return ParsedQuery(query_type=QueryType.LAST_ENTRIES, limit=limit)

    # 4. Period Summary (today, this_week, this_month)
    is_summary = any(
        k in lowered
        for k in (
            "kitna udhaar gaya",
            "kitna udhaar",
            "kitna jama hua",
            "kitna jama",
            "summary",
            "ka hisaab",
            "ka total",
            "ka hisab",
            "today summary",
            "this week",
            "this month",
        )
    )

    # Check if a customer name is present
    # e.g. "Ramesh ka kitna baaki hai", "Ramesh ka total hisaab batao"
    m_cust = re.search(r"(?P<name>[A-Z][A-Za-z]+)\s+(?:ka|ne|ko)\b", text)
    if not m_cust:
        m_eng_cust = re.search(r"\b(?:does|for)\s+(?P<name>[A-Z][A-Za-z]+)\b", text)
        if m_eng_cust:
            m_cust = m_eng_cust

    if m_cust and m_cust.group("name").lower() not in ("aaj", "kal", "parso", "last"):
        cust_name = m_cust.group("name")
        return ParsedQuery(query_type=QueryType.CUSTOMER_BALANCE, customer_name=cust_name)

    if is_summary:
        # Determine period
        period = "today"
        today = date.today()
        start_d = today
        end_d = today

        if any(w in lowered for w in ("hafte", "week", "saptah")):
            period = "this_week"
            start_d = today - timedelta(days=today.weekday())
            end_d = start_d + timedelta(days=6)
        elif any(w in lowered for w in ("mahine", "month")):
            period = "this_month"
            start_d = date(today.year, today.month, 1)
            next_m = today.month % 12 + 1
            next_y = today.year if next_m > 1 else today.year + 1
            end_d = date(next_y, next_m, 1) - timedelta(days=1)

        # Determine metric
        metric = "all"
        if "udhaar" in lowered or "credit" in lowered:
            metric = "credit"
        elif "jama" in lowered or "payment" in lowered or "mila" in lowered:
            metric = "payment"

        return ParsedQuery(
            query_type=QueryType.PERIOD_SUMMARY,
            period=period,
            metric=metric,
            start_date=start_d,
            end_date=end_d,
        )

    # Default fallback to period summary
    return ParsedQuery(query_type=QueryType.PERIOD_SUMMARY, period="today")
