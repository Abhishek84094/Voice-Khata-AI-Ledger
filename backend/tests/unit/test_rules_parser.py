"""Unit tests for deterministic rules parser."""

from datetime import date, timedelta

from app.domain.enums import Direction, Intent
from app.nlu.rules_parser import parse


def test_single_credit_hinglish() -> None:
    r = parse("Ramesh ka 340 udhaar")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Ramesh"
    assert r.events[0].amount_paise == 34000
    assert r.events[0].direction == Direction.CREDIT_GIVEN
    assert r.events[0].occurred_on == date.today()
    assert r.clarification_needed is None


def test_single_payment_hinglish() -> None:
    r = parse("Suresh ne 500 diye")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Suresh"
    assert r.events[0].amount_paise == 50000
    assert r.events[0].direction == Direction.PAYMENT_RECEIVED
    assert r.clarification_needed is None


def test_devanagari_credit() -> None:
    r = parse("रमेश का 340 उधार")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "रमेश"
    assert r.events[0].amount_paise == 34000
    assert r.events[0].direction == Direction.CREDIT_GIVEN


def test_english_credit_and_payment() -> None:
    r1 = parse("Ramesh took 340 on credit")
    assert r1.intent == Intent.RECORD
    assert r1.events[0].customer_name == "Ramesh"
    assert r1.events[0].amount_paise == 34000
    assert r1.events[0].direction == Direction.CREDIT_GIVEN

    r2 = parse("Priya paid 200")
    assert r2.intent == Intent.RECORD
    assert r2.events[0].customer_name == "Priya"
    assert r2.events[0].amount_paise == 20000
    assert r2.events[0].direction == Direction.PAYMENT_RECEIVED


def test_ambiguity_requires_clarification() -> None:
    r1 = parse("Ramesh ko 200 diya")
    assert r1.clarification_needed is not None
    assert len(r1.events) == 0

    r2 = parse("Ramesh ka 300")
    assert r2.clarification_needed is not None
    assert len(r2.events) == 0


def test_undo_and_correction() -> None:
    r_undo = parse("last entry hata do")
    assert r_undo.intent == Intent.UNDO

    r_corr = parse("nahi 430")
    assert r_corr.intent == Intent.CORRECT
    assert len(r_corr.events) == 0


def test_multi_event() -> None:
    r = parse("Ramesh ka 340 udhaar, kal 200 diya tha")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 2
    # Event 1: credit 340 today
    assert r.events[0].customer_name == "Ramesh"
    assert r.events[0].amount_paise == 34000
    assert r.events[0].direction == Direction.CREDIT_GIVEN
    assert r.events[0].occurred_on == date.today()

    # Event 2: payment 200 yesterday
    assert r.events[1].customer_name == "Ramesh"
    assert r.events[1].amount_paise == 20000
    assert r.events[1].direction == Direction.PAYMENT_RECEIVED
    assert r.events[1].occurred_on == date.today() - timedelta(days=1)


def test_pronoun_resolution_with_context() -> None:
    r = parse("isne abhi 800 diye", session_context={"current_customer_name": "Ramesh"})
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Ramesh"
    assert r.events[0].amount_paise == 80000
    assert r.events[0].direction == Direction.PAYMENT_RECEIVED


def test_pronoun_resolution_without_context() -> None:
    r = parse("isne abhi 800 diye", session_context={})
    assert r.clarification_needed == "Kis customer ne?"
    assert len(r.events) == 0


def test_partial_payment_with_promise_and_reason() -> None:
    r = parse("Ramesh ne abhi 800 diye, baaki next week dega, salary late aayi")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Ramesh"
    assert r.events[0].amount_paise == 80000
    assert r.events[0].direction == Direction.PAYMENT_RECEIVED
    assert r.events[0].note == "salary late aayi"
    assert len(r.promises) == 1
    assert r.promises[0].customer_name == "Ramesh"
    assert r.promises[0].due_date == date.today() + timedelta(days=7)


def test_reason_memo_note() -> None:
    r = parse("Geeta ne 300 diye, bimaar thi isliye kam")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Geeta"
    assert r.events[0].amount_paise == 30000
    assert r.events[0].direction == Direction.PAYMENT_RECEIVED
    assert r.events[0].note == "bimaar thi isliye kam"


def test_credit_with_promise() -> None:
    r = parse("Ramesh ka 500 udhaar, Sunday ko wapas dega")
    assert r.intent == Intent.RECORD
    assert len(r.events) == 1
    assert r.events[0].customer_name == "Ramesh"
    assert r.events[0].amount_paise == 50000
    assert r.events[0].direction == Direction.CREDIT_GIVEN
    assert len(r.promises) == 1
    assert r.promises[0].customer_name == "Ramesh"
