"""Unit tests for dialogue templates and spoken response generation (§4.3, §5.10)."""

from app.dialogue.templates import (
    render_clarification_speech,
    render_confirmation_speech,
    render_correction_speech,
    render_overpayment_question,
    render_partial_payment_speech,
    render_saved_card_text,
    render_undo_speech,
)
from app.domain.enums import Direction


def test_credit_confirmation_template() -> None:
    text = render_confirmation_speech(
        customer_name="Ramesh",
        amount_paise=34000,
        direction=Direction.CREDIT_GIVEN,
        balance_paise=34000,
        language="hi-IN",
    )
    assert "Ramesh" in text
    assert "340" in text
    assert "udhaar" in text.lower() or "उधार" in text


def test_payment_confirmation_template() -> None:
    text = render_confirmation_speech(
        customer_name="Suresh",
        amount_paise=50000,
        direction=Direction.PAYMENT_RECEIVED,
        balance_paise=0,
        language="hi-IN",
    )
    assert "Suresh" in text
    assert "500" in text
    assert "jama" in text.lower() or "जमा" in text


def test_saved_card_text() -> None:
    card = render_saved_card_text(
        customer_name="Anita",
        amount_paise=25000,
        direction=Direction.CREDIT_GIVEN,
        balance_paise=25000,
    )
    assert card["customer_name"] == "Anita"
    assert card["amount_formatted"] == "₹250"
    assert card["balance_formatted"] == "₹250"
    assert card["direction_label"] == "Udhaar Diya"


def test_undo_speech_template() -> None:
    text = render_undo_speech(language="hi-IN")
    assert "hata" in text.lower() or "हटा" in text


def test_correction_speech_template() -> None:
    text = render_correction_speech(
        customer_name="Ramesh",
        new_amount_paise=43000,
        new_balance_paise=43000,
        language="hi-IN",
    )
    assert "430" in text
    assert "sudhar" in text.lower() or "सुधार" in text or "badal" in text.lower()


def test_clarification_speech_template() -> None:
    text = render_clarification_speech(
        question="Kaun sa Ramesh: sabziwala ya tailor?",
        language="hi-IN",
    )
    assert "Ramesh" in text


def test_partial_payment_speech_templates() -> None:
    hi = render_partial_payment_speech(
        customer_name="Ramesh",
        paid_paise=80000,
        remaining_paise=120000,
        due_date_str="5 December",
        language="hi-IN",
    )
    assert "800" in hi
    assert "1200" in hi
    assert "5 December" in hi

    hi_no_date = render_partial_payment_speech(
        customer_name="Ramesh",
        paid_paise=80000,
        remaining_paise=120000,
        language="hi-IN",
    )
    assert "800" in hi_no_date
    assert "1200" in hi_no_date

    en = render_partial_payment_speech(
        customer_name="Ramesh",
        paid_paise=80000,
        remaining_paise=120000,
        due_date_str="December 5",
        language="en-IN",
    )
    assert "800" in en
    assert "1200" in en
    assert "December 5" in en

    en_no_date = render_partial_payment_speech(
        customer_name="Ramesh",
        paid_paise=80000,
        remaining_paise=120000,
        language="en-IN",
    )
    assert "800" in en_no_date
    assert "1200" in en_no_date


def test_overpayment_question_templates() -> None:
    hi = render_overpayment_question(
        customer_name="Mohan",
        balance_paise=50000,
        paid_paise=80000,
        language="hi-IN",
    )
    assert "500" in hi
    assert "800" in hi
    assert "300" in hi
    assert "advance" in hi

    en = render_overpayment_question(
        customer_name="Mohan",
        balance_paise=50000,
        paid_paise=80000,
        language="en-IN",
    )
    assert "500" in en
    assert "800" in en
    assert "300" in en
    assert "advance" in en
