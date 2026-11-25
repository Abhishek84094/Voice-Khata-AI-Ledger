"""Templates for short spoken responses and UI card presentation (§4.3 item 7, §5.10)."""

from typing import Any

from app.domain.enums import Direction


def format_rupees(paise: int) -> str:
    """Format paise as integer or decimal rupees string (e.g. ₹340 or ₹340.50)."""
    rupees = paise // 100
    remainder = paise % 100
    if remainder == 0:
        return f"₹{rupees}"
    return f"₹{rupees}.{remainder:02d}"


def render_confirmation_speech(
    customer_name: str,
    amount_paise: int,
    direction: Direction,
    balance_paise: int,
    language: str = "hi-IN",
) -> str:
    """Generate concise spoken confirmation (§4.3 item 7: 'Ramesh, ₹340 udhaar. Ho gaya.')."""
    rupees_num = amount_paise // 100
    if direction == Direction.CREDIT_GIVEN:
        return f"{customer_name}, {rupees_num} rupaye udhaar. Ho gaya."
    else:
        return f"{customer_name} se {rupees_num} rupaye jama. Ho gaya."


def render_saved_card_text(
    customer_name: str,
    amount_paise: int,
    direction: Direction,
    balance_paise: int,
) -> dict[str, Any]:
    """Format structured card payload for instant on-screen rendering."""
    dir_label = "Udhaar Diya" if direction == Direction.CREDIT_GIVEN else "Jama Mila"
    return {
        "customer_name": customer_name,
        "amount_paise": amount_paise,
        "amount_formatted": format_rupees(amount_paise),
        "direction": direction.value,
        "direction_label": dir_label,
        "balance_paise": balance_paise,
        "balance_formatted": format_rupees(balance_paise),
    }


def render_undo_speech(language: str = "hi-IN") -> str:
    """Spoken confirmation for voided transaction."""
    return "Pichli entry hata di gayi hai."


def render_correction_speech(
    customer_name: str,
    new_amount_paise: int,
    new_balance_paise: int,
    language: str = "hi-IN",
) -> str:
    """Spoken confirmation for amended transaction."""
    rupees_num = new_amount_paise // 100
    bal_num = new_balance_paise // 100
    return (
        f"Sudhar kar diya gaya. {customer_name} ka naya amount {rupees_num} rupaye, "
        f"balance {bal_num} rupaye."
    )


def render_clarification_speech(
    question: str,
    language: str = "hi-IN",
) -> str:
    """Read back question requiring human clarification."""
    return question
