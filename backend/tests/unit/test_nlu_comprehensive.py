"""Comprehensive coverage tests for NLU modules (dates, numbers, rules parser)."""

from datetime import date

from app.domain.enums import Direction, Intent
from app.nlu.dates import resolve_date
from app.nlu.numbers import (
    extract_number,
    normalize_amount_paise,
    parse_spoken_number,
)
from app.nlu.rules_parser import parse


def test_dates_edge_cases() -> None:
    today = date.today()

    # "agle Sunday"
    res_next_sun = resolve_date("agle Sunday")
    assert res_next_sun is not None
    assert res_next_sun >= today

    # Explicit date regex
    res_tareekh = resolve_date("15 tareekh ko")
    assert res_tareekh is not None

    # Invalid day like 99 tareekh returns None
    assert resolve_date("99 tareekh ko") is None

    # No date keyword
    assert resolve_date("koi tareekh nahi") is None

    # "aaj" and "abhi"
    assert resolve_date("abhi") == today


def test_numbers_edge_cases() -> None:
    # Empty token list
    val, count = parse_spoken_number([])
    assert val is None and count == 0

    # dhayi sau
    assert normalize_amount_paise("dhayi sau") == 25000
    # paune sau = 75
    assert normalize_amount_paise("paune sau") == 7500
    # sawa do hazaar = 2250
    assert normalize_amount_paise("sawa do hazaar") == 225000
    # saadhe char hazaar = 4500
    assert normalize_amount_paise("saadhe char hazaar") == 450000
    # paune teen hazaar = 2750
    assert normalize_amount_paise("paune teen hazaar") == 275000
    # lakh and crore
    assert normalize_amount_paise("do lakh") == 20000000
    assert normalize_amount_paise("ek crore") == 1000000000
    # sawa alone with units
    assert normalize_amount_paise("sawa teen") == 32500
    assert normalize_amount_paise("saadhe teen") == 35000
    assert normalize_amount_paise("paune teen") == 27500
    # scale alone
    assert normalize_amount_paise("sau") == 10000
    assert normalize_amount_paise("hazaar") == 100000

    # Extract number not found
    assert extract_number("kisi ka naam nahi") is None


def test_rules_parser_edge_cases() -> None:
    # English 'and' multi-event
    r_and = parse("Ramesh took 300 on credit and Suresh paid 200")
    assert r_and.intent == Intent.RECORD
    assert len(r_and.events) == 2
    assert r_and.events[0].customer_name == "Ramesh"
    assert r_and.events[0].amount_paise == 30000
    assert r_and.events[0].direction == Direction.CREDIT_GIVEN
    assert r_and.events[1].customer_name == "Suresh"
    assert r_and.events[1].amount_paise == 20000
    assert r_and.events[1].direction == Direction.PAYMENT_RECEIVED

    # "Received 500 from Suresh"
    r_from = parse("Received 500 from Suresh")
    assert r_from.intent == Intent.RECORD
    assert r_from.events[0].customer_name == "Suresh"
    assert r_from.events[0].amount_paise == 50000
    assert r_from.events[0].direction == Direction.PAYMENT_RECEIVED

    # "Add 500 credit for Arun"
    r_for = parse("Add 500 credit for Arun")
    assert r_for.intent == Intent.RECORD
    assert r_for.events[0].customer_name == "Arun"
    assert r_for.events[0].amount_paise == 50000
    assert r_for.events[0].direction == Direction.CREDIT_GIVEN

    # Missing direction words in single clause -> clarification
    r_amb = parse("Ramesh 500")
    assert r_amb.clarification_needed is not None

    # Unrecognized clause
    r_empty = parse("kuch bhi random text bina number ke")
    assert r_empty.clarification_needed is not None
