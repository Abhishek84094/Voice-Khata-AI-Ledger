"""Relative and absolute date resolver for Hindi, Hinglish, and English."""

from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS = {
    # English
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
    # Hindi
    "somvar": 0,
    "somvaar": 0,
    "सोमवार": 0,
    "mangalvar": 1,
    "mangalvaar": 1,
    "मंगलवार": 1,
    "budhvar": 2,
    "budhvaar": 2,
    "बुधवार": 2,
    "guruvar": 3,
    "guruvaar": 3,
    "brihaspativar": 3,
    "गुरुवार": 3,
    "shukravar": 4,
    "shukravaar": 4,
    "शुक्रवार": 4,
    "shanivar": 5,
    "shanivaar": 5,
    "शनिवार": 5,
    "ravivar": 6,
    "ravivaar": 6,
    "रविवार": 6,
    "itvar": 6,
    "इतवार": 6,
}

PAST_INDICATORS = {
    "diya tha",
    "diya",
    "diye the",
    "diye",
    "aaya",
    "aaye",
    "jama tha",
    "mila",
    "mila tha",
    "paid",
    "gave",
    "tha",
    "the",
    "thi",
    "दिया था",
    "दिया",
    "दिए थे",
    "दिए",
    "आया",
    "जमा था",
    "मिला",
    "था",
    "थे",
    "थी",
}

FUTURE_INDICATORS = {
    "dega",
    "degi",
    "denge",
    "lauta dega",
    "wapas",
    "tak",
    "ko dega",
    "next week",
    "agle hafte",
    "agle mahine",
    "tomorrow",
    "due",
    "देगा",
    "देगी",
    "देंगे",
    "लौटा देगा",
    "वापस",
    "तक",
}


def resolve_date(text: str, reference_date: date | None = None) -> date | None:
    """Resolve a relative or spoken date into a concrete date."""
    ref = reference_date or date.today()
    lowered = text.lower()

    # Aaj / today
    if any(k in lowered for k in ("aaj", "आज", "today", "abhi")):
        return ref

    # Parso / parson
    if any(k in lowered for k in ("parso", "परसों", "परसो", "parson")):
        is_past = any(p in lowered for p in PAST_INDICATORS)
        is_future = any(f in lowered for f in FUTURE_INDICATORS)
        if is_past and not is_future:
            return ref - timedelta(days=2)
        return ref + timedelta(days=2)

    # Kal
    if any(k in lowered for k in ("kal", "कल", "yesterday", "tomorrow")):
        if "yesterday" in lowered:
            return ref - timedelta(days=1)
        if "tomorrow" in lowered:
            return ref + timedelta(days=1)
        is_past = any(p in lowered for p in PAST_INDICATORS)
        is_future = any(f in lowered for f in FUTURE_INDICATORS)
        if is_past and not is_future:
            return ref - timedelta(days=1)
        if is_future and not is_past:
            return ref + timedelta(days=1)
        # Contextual default: if 'udhaar' without past indicator, usually future promise or today
        return ref - timedelta(days=1)

    # Weekdays
    for name, target_wd in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            # Find next upcoming occurrence of target_wd
            days_ahead = (target_wd - ref.weekday()) % 7
            if days_ahead == 0 and any(f in lowered for f in ("agle", "next")):
                days_ahead = 7
            return ref + timedelta(days=days_ahead)

    # Explicit day of month (e.g. "15 tareekh", "5 ko")
    m = re.search(r"(\d{1,2})\s*(?:tareekh|tarikh|तारीख)", lowered)
    if m:
        day = int(m.group(1))
        try:
            target_date = ref.replace(day=day)
            if target_date < ref:
                # Move to next month
                month = ref.month % 12 + 1
                year = ref.year if month > 1 else ref.year + 1
                target_date = date(year, month, day)
            return target_date
        except ValueError:
            return None

    return None
