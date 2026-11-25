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


def render_partial_payment_speech(
    customer_name: str,
    paid_paise: int,
    remaining_paise: int,
    due_date_str: str | None = None,
    language: str = "hi-IN",
) -> str:
    """Read back after partial payment commit (§5.10 item 7).

    e.g. 'Ramesh ne ₹800 diye. Baaki ₹1,200, 5 December tak.'
    """
    paid_num = paid_paise // 100
    rem_num = remaining_paise // 100
    if language.startswith("en"):
        if due_date_str:
            return f"{customer_name} paid ₹{paid_num}. Remaining ₹{rem_num}, due by {due_date_str}."
        return f"{customer_name} paid ₹{paid_num}. Remaining balance is ₹{rem_num}."

    if due_date_str:
        return f"{customer_name} ne ₹{paid_num} diye. Baaki ₹{rem_num}, {due_date_str} tak."
    return f"{customer_name} ne ₹{paid_num} diye. Baaki balance ₹{rem_num} hai."


def render_overpayment_question(
    customer_name: str,
    balance_paise: int,
    paid_paise: int,
    language: str = "hi-IN",
) -> str:
    """Prompt for overpayment confirmation (§5.10 item 6).

    e.g. 'Balance ₹500 hai, ₹800 mila. Baaki ₹300 advance likh doon?'
    """
    bal_num = balance_paise // 100
    paid_num = paid_paise // 100
    adv_num = paid_num - bal_num
    if language.startswith("en"):
        return (
            f"Balance is ₹{bal_num}, received ₹{paid_num}. Record remaining ₹{adv_num} as advance?"
        )
    return f"Balance ₹{bal_num} hai, ₹{paid_num} mila. Baaki ₹{adv_num} advance likh doon?"


def render_customer_balance_speech(
    customer_name: str,
    balance_paise: int,
    language: str = "hi-IN",
) -> str:
    """Spoken answer for a customer's outstanding balance or advance (§4.3 item 11)."""
    bal_num = balance_paise // 100
    if balance_paise > 0:
        if language.startswith("en"):
            return f"{customer_name} owes ₹{bal_num}."
        return f"{customer_name} ka ₹{bal_num} baaki hai."
    elif balance_paise < 0:
        adv_num = abs(bal_num)
        if language.startswith("en"):
            return f"{customer_name} has ₹{adv_num} advance."
        return f"{customer_name} ka ₹{adv_num} advance jama hai."
    else:
        if language.startswith("en"):
            return f"{customer_name}'s account is settled."
        return f"{customer_name} ka hisaab barabar hai, koi baaki nahi."


def render_period_summary_speech(
    summary: Any,
    language: str = "hi-IN",
) -> str:
    """Spoken period summary (today, this week, this month)."""
    cr_num = summary.credit_paise // 100
    pay_num = summary.payment_paise // 100
    p = summary.period

    if language.startswith("en"):
        period_str = (
            "Today" if p == "today" else ("This week" if p == "this_week" else "This month")
        )
        return (
            f"{period_str}, total credit given is ₹{cr_num}, and payments received are ₹{pay_num}."
        )

    period_str = "Aaj" if p == "today" else ("Is hafte" if p == "this_week" else "Is mahine")
    return f"{period_str} kul ₹{cr_num} ka udhaar gaya, aur ₹{pay_num} jama hue."


def render_top_debtors_speech(
    debtors: list[Any],
    language: str = "hi-IN",
) -> str:
    """Spoken answer listing customers with highest outstanding balances."""
    if not debtors:
        if language.startswith("en"):
            return "No customers have outstanding credit."
        return "Kisi customer ka udhaar baaki nahi hai."

    items_str = []
    for d in debtors[:3]:
        amt = d.balance_paise // 100
        items_str.append(f"{d.customer_name} (₹{amt})")

    joined = " aur ".join(items_str) if len(items_str) > 1 else items_str[0]
    if language.startswith("en"):
        joined_en = " and ".join(items_str) if len(items_str) > 1 else items_str[0]
        return f"Top debtors are {joined_en}."
    return f"Sabse zyada udhaar {joined} ka hai."


def render_due_today_speech(
    dues: list[Any],
    language: str = "hi-IN",
) -> str:
    """Spoken answer for promises due today."""
    if not dues:
        if language.startswith("en"):
            return "No payments are due today."
        return "Aaj kisi ka payment due nahi hai."

    items_str = [f"{d.customer_name} ka ₹{d.remaining_paise // 100}" for d in dues[:3]]
    joined = " aur ".join(items_str)
    if language.startswith("en"):
        items_en = [f"{d.customer_name} (₹{d.remaining_paise // 100})" for d in dues[:3]]
        return f"Payments due today: {', '.join(items_en)}."
    return f"Aaj {joined} ka payment due hai."


def render_overdue_speech(
    overdues: list[Any],
    language: str = "hi-IN",
) -> str:
    """Spoken answer for overdue promises."""
    if not overdues:
        if language.startswith("en"):
            return "No overdue payments."
        return "Koi overdue payment nahi hai."

    items_str = [f"{d.customer_name} ka ₹{d.remaining_paise // 100}" for d in overdues[:3]]
    joined = " aur ".join(items_str)
    if language.startswith("en"):
        items_en = [f"{d.customer_name} (₹{d.remaining_paise // 100})" for d in overdues[:3]]
        return f"Overdue payments: {', '.join(items_en)}."
    return f"{joined} overdue hai."
