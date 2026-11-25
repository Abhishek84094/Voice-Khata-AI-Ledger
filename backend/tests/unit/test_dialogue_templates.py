"""Unit tests for dialogue templates and spoken response generation (§4.3, §5.10)."""

from app.dialogue.templates import (
    render_clarification_speech,
    render_confirmation_speech,
    render_correction_speech,
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
