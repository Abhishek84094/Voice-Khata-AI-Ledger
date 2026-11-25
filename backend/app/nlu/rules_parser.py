"""Deterministic rules parser for Voice Khata utterances.

Processes single-event, multi-event, queries, undo, corrections, and disambiguation.
Runs in microseconds with zero network I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.compliance.guardrails import is_out_of_scope
from app.domain.enums import Direction, Intent
from app.nlu.dates import resolve_date
from app.nlu.numbers import extract_number


@dataclass
class ParsedEvent:
    customer_name: str
    amount_paise: int
    direction: Direction
    occurred_on: date = field(default_factory=date.today)
    note: str | None = None


@dataclass
class ParseResult:
    intent: Intent
    events: list[ParsedEvent] = field(default_factory=list)
    clarification_needed: str | None = None
    out_of_scope: bool = False


CREDIT_KEYWORDS = [
    "udhaar",
    "udhar",
    "baaki",
    "baki",
    "credit",
    "on credit",
    "likh do",
    "likho",
    "उधार",
    "बाकी",
    "लिख दो",
    "लिखो",
]

PAYMENT_KEYWORDS = [
    "diya",
    "diye",
    "diye the",
    "diya tha",
    "jama",
    "jama kiya",
    "jama kiye",
    "jama tha",
    "aaya",
    "aaye",
    "mila",
    "mila tha",
    "paid",
    "received",
    "gave",
    "दिए",
    "दिया",
    "दिए थे",
    "दिया था",
    "जमा",
    "जमा किया",
    "जमा किए",
    "जमा था",
    "आया",
    "आए",
    "मिला",
    "मिला था",
]

UNDO_PATTERNS = [
    r"\bundo\b",
    r"\blast\s*entry\s*hata\s*do\b",
    r"\bcancel\s*kar\s*do\b",
    r"\bhata\s*do\b",
    r"आखिरी\s*एंट्री\s*हटा\s*दो",
    r"हटा\s*दो",
]

CORRECTION_PATTERNS = [
    r"^(?:nahi|nahin|sorry|no\s*i\s*meant|galat\s*tha)\b",
    r"^(?:नहीं|ग़लत\s*था)(?:$|\s|[।,])",
]

QUERY_PATTERNS = [
    r"\btotal\b",
    r"\bkitna\s*udhaar\b",
    r"\bkitna\s*baaki\b",
    r"\bkitna\s*dena\b",
    r"\bhisab\s*batao\b",
    r"कुल\s*कितना",
    r"कितना\s*बाकी",
    r"कितना\s*उधार",
]


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"(\d),(\d)", r"\1\2", text)
    return cleaned.strip()


def _is_undo(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in UNDO_PATTERNS)


def _is_correction(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in CORRECTION_PATTERNS)


def _is_query(text: str) -> bool:
    lowered = text.lower()
    if "?" in text:
        return True
    return any(re.search(p, lowered) for p in QUERY_PATTERNS)


def _has_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    for k in keywords:
        pattern = rf"(?:^|\s|[।,]|\b){re.escape(k)}(?:$|\s|[।,]|\b)"
        if re.search(pattern, lowered):
            return True
    return False


def _extract_customer_from_clause(clause: str) -> str | None:
    # 1. Devanagari pattern: "रमेश का", "सुरेश ने", "गीता को"
    m_dev = re.search(
        r"(?:^|\s)(?P<name>[\u0900-\u097F]+(?:\s+जी)?)\s+(?:का|ने|को)(?:$|\s|[।,])",
        clause,
    )
    if m_dev:
        name = m_dev.group("name").strip()
        if name not in ("आज", "कल", "परसों", "आखिरी"):
            return name

    # 2. Latin postposition pattern: "Ramesh ka", "Suresh ne", "Anita ji ne", "Geeta ko"
    m_lat = re.search(
        r"(?:^|\s)(?P<name>[A-Z][A-Za-z]*(?:\s+ji)?)\s+(?:ka|ne|ko)\b",
        clause,
    )
    if m_lat:
        name = m_lat.group("name").strip()
        if name.lower() not in ("aaj", "kal", "parso", "last", "aath", "barah", "paanch", "char"):
            return name

    # 3. English prepositional patterns:
    # "Credit 340 to Ramesh", "Add 500 credit for Arun"
    m = re.search(r"\b(?:for|to)\s+(?P<name>[A-Z][A-Za-z]+)\b", clause)
    if m:
        return m.group("name").strip()

    # "Received 500 from Suresh"
    m = re.search(r"\bfrom\s+(?P<name>[A-Z][A-Za-z]+)\b", clause)
    if m:
        return m.group("name").strip()

    # English subject patterns: "Ramesh took ...", "Priya paid ...", "Meena gave ..."
    m = re.search(
        r"^(?:add\s+)?(?P<name>[A-Z][A-Za-z]+)\s+(?:took|paid|gave|three|two|one|four|five|\d+)\b",
        clause.strip(),
    )
    if m:
        name = m.group("name").strip()
        if name.lower() not in ("add", "credit", "received", "yesterday", "today"):
            return name

    # 4. Postposition at end: "dedh sau udhaar Geeta ko", "गीता को डेढ़ सौ उधार"
    m_end = re.search(
        r"(?P<name>[A-Z\u0900-\u097F][A-Za-z\u0900-\u097F]*)\s+(?:ko|को)(?:$|\s|[।,])",
        clause,
    )
    if m_end:
        name = m_end.group("name").strip()
        if name.lower() not in ("kal", "aaj", "parso", "कल", "आज"):
            return name

    return None


def _extract_direction_from_clause(clause: str) -> Direction | None:
    lowered = clause.lower()

    # Check for ambiguous marker "ko ... diya": e.g. "Ramesh ko 200 diya"
    if re.search(r"(?:^|\s)(?:ko|को)\s+.*(?:diya|diye|दिए|दिया)", lowered):
        return None

    has_credit = _has_keyword(clause, CREDIT_KEYWORDS)
    has_payment = _has_keyword(clause, PAYMENT_KEYWORDS)

    if has_credit and not has_payment:
        return Direction.CREDIT_GIVEN
    if has_payment and not has_credit:
        return Direction.PAYMENT_RECEIVED
    return None


def _parse_single_clause(
    clause: str,
    inherited_customer: str | None = None,
    default_direction: Direction | None = None,
) -> ParsedEvent | None:
    # 1. Amount
    num_res = extract_number(clause)
    if num_res is None:
        return None
    amount_paise, _ = num_res

    # 2. Customer
    customer = _extract_customer_from_clause(clause) or inherited_customer
    if not customer:
        return None

    # 3. Direction
    direction = _extract_direction_from_clause(clause) or default_direction
    if not direction:
        return None

    # 4. Date
    d = resolve_date(clause)
    if d is None:
        d = date.today()

    return ParsedEvent(
        customer_name=customer,
        amount_paise=amount_paise,
        direction=direction,
        occurred_on=d,
    )


def parse(text: str) -> ParseResult:
    """Parse utterance into structured ParseResult with microsecond execution."""
    cleaned = _clean_text(text)

    # 1. Guardrail check
    if is_out_of_scope(cleaned):
        return ParseResult(intent=Intent.OTHER, out_of_scope=True)

    # 2. Undo intent
    if _is_undo(cleaned):
        return ParseResult(intent=Intent.UNDO)

    # 3. Correction intent
    if _is_correction(cleaned):
        return ParseResult(intent=Intent.CORRECT, events=[])

    # 4. Query intent
    if _is_query(cleaned):
        return ParseResult(intent=Intent.QUERY)

    # 5. Check ambiguity
    # e.g. "Ramesh ko 200 diya", "Ramesh ka 300", "Suresh 400", "Geeta ka 150"
    lowered = cleaned.lower()
    if re.search(r"(?:^|\s)(?:ko|को)\s+.*(?:diya|diye|दिए|दिया)", lowered):
        return ParseResult(
            intent=Intent.RECORD,
            clarification_needed="Direction is ambiguous: was money given or received?",
        )

    # Missing direction words check in single-clause utterances:
    has_credit = _has_keyword(cleaned, CREDIT_KEYWORDS)
    has_payment = _has_keyword(cleaned, PAYMENT_KEYWORDS)
    if not has_credit and not has_payment and not ("," in cleaned or " aur " in cleaned):
        return ParseResult(
            intent=Intent.RECORD,
            clarification_needed="Missing direction: is this udhaar or payment?",
        )

    # 6. Multi-event splitting (by comma or 'aur')
    clauses: list[str] = []
    if "," in cleaned:
        clauses = [c.strip() for c in cleaned.split(",") if c.strip()]
    elif " aur " in cleaned:
        clauses = [c.strip() for c in cleaned.split(" aur ") if c.strip()]
    elif " and " in cleaned:
        clauses = [c.strip() for c in cleaned.split(" and ") if c.strip()]
    else:
        clauses = [cleaned]

    events: list[ParsedEvent] = []
    last_customer: str | None = None

    for c in clauses:
        ev = _parse_single_clause(c, inherited_customer=last_customer)
        if ev is not None:
            events.append(ev)
            last_customer = ev.customer_name

    if events:
        return ParseResult(intent=Intent.RECORD, events=events)

    return ParseResult(
        intent=Intent.RECORD,
        clarification_needed="Could not determine customer or amount with certainty.",
    )
