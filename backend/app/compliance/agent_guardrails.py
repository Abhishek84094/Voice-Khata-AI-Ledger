"""Agent safety guardrails (§6 Phase 9).

Rules:
1. LLM never calculates: numbers and balances are strictly derived by deterministic code.
2. Outbound messages require explicit shopkeeper approval.
3. Only opted-in customers may receive reminder drafts.
4. Maximum 1 reminder per customer per N days (default 3 days).
5. Quiet hours enforcement (e.g. 21:00 to 08:00 local time).
6. Banned-phrase lint on all reminder drafts (no threats, shame, legal action, or pressure).
7. Prompt injection defense: customer names, notes, and transcripts are treated as data.
8. Payment reasons / notes are NEVER used to judge, shame, or score customers.
"""

from __future__ import annotations

import re
from datetime import datetime

# Banned phrases in reminders (§6 Phase 9: no threats, shame, police, legal, insult)
BANNED_PHRASES = [
    r"\bpolice\b",
    r"\bcase\b",
    r"\bcourt\b",
    r"\blegal\b",
    r"\bshame\b",
    r"\bchindi\b",
    r"\bchor\b",
    r"\bdhoka\b",
    r"\bjail\b",
    r"\bthreat\b",
    r"\bwarna\b",
    r"\baction\b",
    r"\bpolice\s*complaint\b",
    r"केस",
    r"कोर्ट",
    r"पुलिस",
    r"धोखा",
    r"चोर",
    r"वरना",
]


def check_banned_phrases(text: str) -> list[str]:
    """Return any banned aggressive/threatening phrases found in text."""
    found: list[str] = []
    lowered = text.lower()
    for p in BANNED_PHRASES:
        m = re.search(p, lowered)
        if m:
            found.append(m.group(0))
    return found


def is_within_quiet_hours(
    now: datetime,
    quiet_start_hour: int = 21,
    quiet_end_hour: int = 8,
) -> bool:
    """Check if the given datetime falls within quiet hours (e.g. 9 PM to 8 AM)."""
    hour = now.hour
    if quiet_start_hour > quiet_end_hour:
        # Crosses midnight: e.g. 21..23 or 0..7
        return hour >= quiet_start_hour or hour < quiet_end_hour
    else:
        return quiet_start_hour <= hour < quiet_end_hour


def sanitize_prompt_data(data: str) -> str:
    """Strip instruction-like prefixes from customer names and notes to prevent prompt injection."""
    cleaned = data.strip()
    # Strip common system prompt override patterns
    cleaned = re.sub(
        r"(?i)^(?:system\s*:|user\s*:|assistant\s*:|ignore\s*previous\s*instructions|act\s*as)\s*",
        "",
        cleaned,
    )
    return cleaned.strip()
