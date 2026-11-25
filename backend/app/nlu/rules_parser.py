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
class ParsedPromise:
    customer_name: str
    amount_paise: int | None  # None = remainder / whole balance
    due_date: date


@dataclass
class ParseResult:
    intent: Intent
    events: list[ParsedEvent] = field(default_factory=list)
    promises: list[ParsedPromise] = field(default_factory=list)
    clarification_needed: str | None = None
    out_of_scope: bool = False


@dataclass
class ParseUtteranceResult:
    action: str  # "record", "undo", "correct", "query", "clarification_needed", "out_of_scope"
    intent: Intent
    events: list[ParsedEvent] = field(default_factory=list)
    promises: list[ParsedPromise] = field(default_factory=list)
    customer_name: str | None = None
    question: str | None = None
    options: list[str] = field(default_factory=list)
    out_of_scope: bool = False
    note: str | None = None


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


PRONOUN_WORDS = {
    "isne",
    "usne",
    "wo",
    "woh",
    "voh",
    "he",
    "she",
    "इसने",
    "उसने",
    "वो",
    "वह",
}

PROMISE_KEYWORDS = [
    "dega",
    "degi",
    "denge",
    "lauta dega",
    "lauta degi",
    "lauta denge",
    "wapas",
    "baaki",
    "baki",
    "देगा",
    "देगी",
    "देंगे",
    "लौटा देगा",
    "लौटा देगी",
    "लौटा देंगे",
    "वापस",
    "बाकी",
]


DATE_WORDS = {
    "aaj",
    "kal",
    "parso",
    "parson",
    "last",
    "today",
    "tomorrow",
    "yesterday",
    "sunday",
    "sun",
    "monday",
    "mon",
    "tuesday",
    "tue",
    "wednesday",
    "wed",
    "thursday",
    "thu",
    "friday",
    "fri",
    "saturday",
    "sat",
    "somvar",
    "somvaar",
    "mangalvar",
    "mangalvaar",
    "budhvar",
    "budhvaar",
    "guruvar",
    "guruvaar",
    "shukravar",
    "shukravaar",
    "shanivar",
    "shanivaar",
    "ravivar",
    "ravivaar",
    "itvar",
    "tareekh",
    "tarikh",
    "hafta",
    "hafte",
    "week",
    "mahine",
    "month",
    "baaki",
    "baki",
    "आज",
    "कल",
    "परसों",
    "आखिरी",
    "सोमवार",
    "मंगलवार",
    "बुधवार",
    "गुरुवार",
    "शुक्रवार",
    "शनिवार",
    "रविवार",
    "इतवार",
    "तारीख",
    "बाकी",
    "हफ्ते",
    "महीने",
}


def _has_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    for k in keywords:
        pattern = rf"(?:^|\s|[।,]|\b){re.escape(k)}(?:$|\s|[।,]|\b)"
        if re.search(pattern, lowered):
            return True
    return False


def _extract_customer_from_clause(clause: str) -> str | None:
    # 0. Check pronouns: "isne abhi 800 diye", "wo kal dega", "usne 500 diye"
    lowered_clause = clause.lower().strip()
    words = lowered_clause.split()
    if words and words[0] in PRONOUN_WORDS:
        return "__PRONOUN__"

    # 1. Devanagari pattern: "रमेश का", "सुरेश ने", "गीता को"
    m_dev = re.search(
        r"(?:^|\s)(?P<name>[\u0900-\u097F]+(?:\s+जी)?)\s+(?:का|ने|को)(?:$|\s|[।,])",
        clause,
    )
    if m_dev:
        name = m_dev.group("name").strip()
        if name in PRONOUN_WORDS:
            return "__PRONOUN__"
        if name not in DATE_WORDS:
            return name

    # 2. Latin postposition pattern: "Ramesh ka", "Suresh ne", "Anita ji ne", "Geeta ko"
    m_lat = re.search(
        r"(?:^|\s)(?P<name>[A-Za-z]+(?:\s+ji)?)\s+(?:ka|ne|ko)\b",
        clause,
        re.IGNORECASE,
    )
    if m_lat:
        name = m_lat.group("name").strip()
        if name.lower() in PRONOUN_WORDS:
            return "__PRONOUN__"
        if name.lower() not in DATE_WORDS and name.lower() not in (
            "aath",
            "barah",
            "paanch",
            "char",
            "sau",
            "hazaar",
        ):
            return name

    # 3. English prepositional patterns:
    # "Credit 340 to Ramesh", "Add 500 credit for Arun"
    m = re.search(r"\b(?:for|to)\s+(?P<name>[A-Z][A-Za-z]+)\b", clause)
    if m:
        name = m.group("name").strip()
        if name.lower() not in DATE_WORDS:
            return name

    # "Received 500 from Suresh"
    m = re.search(r"\bfrom\s+(?P<name>[A-Z][A-Za-z]+)\b", clause)
    if m:
        name = m.group("name").strip()
        if name.lower() not in DATE_WORDS:
            return name

    # English subject patterns: "Ramesh took ...", "Priya paid ...", "Meena gave ..."
    m = re.search(
        r"^(?:add\s+)?(?P<name>[A-Z][A-Za-z]+)\s+(?:took|paid|gave|three|two|one|four|five|\d+)\b",
        clause.strip(),
    )
    if m:
        name = m.group("name").strip()
        if name.lower() not in DATE_WORDS and name.lower() not in (
            "add",
            "credit",
            "received",
            "yesterday",
            "today",
        ):
            return name

    # 4. Postposition at end: "dedh sau udhaar Geeta ko", "गीता को डेढ़ सौ उधार"
    m_end = re.search(
        r"(?P<name>[A-Z\u0900-\u097F][A-Za-z\u0900-\u097F]*)\s+(?:ko|को)(?:$|\s|[।,])",
        clause,
    )
    if m_end:
        name = m_end.group("name").strip()
        if name.lower() not in DATE_WORDS:
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


def parse(
    text: str,
    session_context: dict[str, str | None] | None = None,
) -> ParseResult:
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
            clarification_needed="Direction is ambiguous: was this udhaar or payment (jama)?",
        )

    # Missing direction words check in single-clause utterances:
    has_credit = _has_keyword(cleaned, CREDIT_KEYWORDS)
    has_payment = _has_keyword(cleaned, PAYMENT_KEYWORDS)
    has_promise = _has_keyword(cleaned, PROMISE_KEYWORDS)
    if (
        not has_credit
        and not has_payment
        and not has_promise
        and not ("," in cleaned or " aur " in cleaned)
    ):
        return ParseResult(
            intent=Intent.RECORD,
            clarification_needed="Missing direction: is this udhaar or payment?",
        )

    # 6. Multi-event and promise splitting (by comma or 'aur')
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
    promises: list[ParsedPromise] = []
    notes: list[str] = []
    last_customer: str | None = None

    for c in clauses:
        # Check if clause is a promise clause
        is_prom_clause = _has_keyword(c, PROMISE_KEYWORDS)
        ev = _parse_single_clause(c, inherited_customer=last_customer)
        if ev is not None:
            events.append(ev)
            last_customer = ev.customer_name
            # If the event itself also has a future promise word (e.g. single clause with promise)
            if is_prom_clause:
                p_date = resolve_date(c)
                if p_date and p_date > date.today():
                    promises.append(
                        ParsedPromise(
                            customer_name=ev.customer_name,
                            amount_paise=ev.amount_paise,
                            due_date=p_date,
                        )
                    )
        elif is_prom_clause:
            # Standalone promise clause e.g. "Sunday ko wapas dega", "baaki next week dega"
            p_date = resolve_date(c)
            cust = _extract_customer_from_clause(c) or last_customer
            num_res = extract_number(c)
            p_amt = num_res[0] if num_res else None
            if p_date:
                promises.append(
                    ParsedPromise(
                        customer_name=cust or "",
                        amount_paise=p_amt,
                        due_date=p_date,
                    )
                )
        else:
            # Explanatory note clause e.g. "salary late aayi", "bimaar thi isliye kam"
            num_res = extract_number(c)
            if (
                num_res is None
                and not _has_keyword(c, CREDIT_KEYWORDS)
                and not _has_keyword(c, PAYMENT_KEYWORDS)
            ):
                notes.append(c.strip())

    # Attach notes to events if any
    if notes and events:
        combined_note = "; ".join(notes)
        for ev in events:
            ev.note = combined_note

    # Pronoun resolution
    ctx_cust = (session_context or {}).get("current_customer_name")
    for ev in events:
        if ev.customer_name == "__PRONOUN__":
            if ctx_cust:
                ev.customer_name = ctx_cust
            else:
                return ParseResult(
                    intent=Intent.RECORD,
                    clarification_needed="Kis customer ne?",
                )

    for pr in promises:
        if pr.customer_name == "__PRONOUN__" or not pr.customer_name:
            if ctx_cust:
                pr.customer_name = ctx_cust
            elif events:
                pr.customer_name = events[0].customer_name
            else:
                return ParseResult(
                    intent=Intent.RECORD,
                    clarification_needed="Kis customer ne?",
                )

    if events or promises:
        return ParseResult(intent=Intent.RECORD, events=events, promises=promises)

    return ParseResult(
        intent=Intent.RECORD,
        clarification_needed="Could not determine customer or amount with certainty.",
    )


def parse_utterance(
    text: str,
    session_context: dict[str, str | None] | None = None,
) -> ParseUtteranceResult:
    """Session-aware wrapper around pure parse() mapping to pipeline actions (§4.3 item 4)."""
    p = parse(text, session_context=session_context)

    if p.out_of_scope:
        return ParseUtteranceResult(
            action="out_of_scope",
            intent=Intent.OTHER,
            out_of_scope=True,
            question="Voice Khata keval udhaar aur hisaab ke liye hai.",
        )

    if p.intent == Intent.UNDO:
        return ParseUtteranceResult(
            action="undo",
            intent=Intent.UNDO,
        )

    if p.intent == Intent.CORRECT:
        num_res = extract_number(text)
        amt = num_res[0] if num_res is not None else None
        evs: list[ParsedEvent] = []
        if amt is not None:
            ctx_cust = (session_context or {}).get("current_customer_name") or ""
            evs = [
                ParsedEvent(customer_name=ctx_cust, amount_paise=amt, direction=Direction.AMENDED)
            ]
        return ParseUtteranceResult(
            action="correct",
            intent=Intent.CORRECT,
            events=evs,
        )

    if p.intent == Intent.QUERY:
        cust = _extract_customer_from_clause(text)
        return ParseUtteranceResult(
            action="query",
            intent=Intent.QUERY,
            customer_name=cust,
        )

    if p.clarification_needed:
        opts = ["Udhaar", "Jama"] if "direction" in p.clarification_needed.lower() else []
        return ParseUtteranceResult(
            action="clarification_needed",
            intent=p.intent,
            question=p.clarification_needed,
            options=opts,
        )

    if p.intent == Intent.RECORD and (p.events or p.promises):
        c_name = (
            p.events[0].customer_name
            if p.events
            else (p.promises[0].customer_name if p.promises else None)
        )
        return ParseUtteranceResult(
            action="record",
            intent=Intent.RECORD,
            events=p.events,
            promises=p.promises,
            customer_name=c_name,
        )

    return ParseUtteranceResult(
        action="clarification_needed",
        intent=Intent.RECORD,
        question="Kripya dobara bolein.",
    )
