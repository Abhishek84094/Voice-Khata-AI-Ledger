"""Compliance guardrails enforcing domain scope and regulatory boundaries (§1 rule 9)."""

import re

OUT_OF_SCOPE_PATTERNS = [
    # Lending / personal loans
    r"\bloan\b",
    r"\bकर्ज\b",
    r"\bउधार\s*चाहिए\b",
    r"\bneed\s*(?:a\s*)?loan\b",
    # Interest calculations
    r"\binterest\b",
    r"\bbyaj\b",
    r"\bbiyaj\b",
    r"\bब्याज\b",
    # Credit scoring
    r"\bcibil\b",
    r"\bcredit\s*score\b",
    # Non-khata personal/medical/external queries
    r"\bdoctor\b",
    r"\bडॉक्टर\b",
    r"\bweather\b",
    r"\bmausam\b",
    r"\bjoke\b",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in OUT_OF_SCOPE_PATTERNS]


def is_out_of_scope(text: str) -> bool:
    """Return True if utterance touches banned non-khata capabilities."""
    lowered = text.lower()
    for pattern in COMPILED_PATTERNS:
        if pattern.search(lowered):
            return True
    return False
