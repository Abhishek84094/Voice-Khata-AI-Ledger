"""Unit tests for out-of-scope compliance guardrails (§1, §5.1)."""

from app.compliance.guardrails import is_out_of_scope


def test_lending_and_loan_blocked() -> None:
    assert is_out_of_scope("mujhe loan chahiye") is True
    assert is_out_of_scope("shopkeeper loan de do") is True


def test_interest_and_credit_scoring_blocked() -> None:
    assert is_out_of_scope("Ramesh ka interest kitna hua") is True
    assert is_out_of_scope("mera CIBIL score batao") is True
    assert is_out_of_scope("credit score kya hai") is True


def test_legitimate_ledger_not_blocked() -> None:
    assert is_out_of_scope("Ramesh ka 340 udhaar") is False
    assert is_out_of_scope("Suresh ne 500 diye") is False
    assert is_out_of_scope("Ramesh ka total?") is False
    assert is_out_of_scope("aaj kitna udhaar gaya") is False
    assert is_out_of_scope("last entry hata do") is False
    assert is_out_of_scope("nahi 430") is False
