"""Hypothesis property tests for number normalization invariants (§2, §5.4)."""

from app.nlu.numbers import normalize_amount_paise
from hypothesis import given
from hypothesis import strategies as st


@given(st.text())
def test_normalizer_never_crashes(text: str) -> None:
    # Rule: normalizer never raises an unhandled exception on any input
    result = normalize_amount_paise(text)
    assert result is None or isinstance(result, int)
    if isinstance(result, int):
        assert result >= 0


@given(st.integers(min_value=1, max_value=999999))
def test_digits_roundtrip(val: int) -> None:
    # Rule: every standard integer digits string round-trips correctly
    paise = normalize_amount_paise(str(val))
    assert paise == val * 100


def test_unknown_number_token_returns_none() -> None:
    # Rule: an unknown number token anywhere returns None, NEVER a partial value
    assert normalize_amount_paise("chaarxyz sau") is None
    assert normalize_amount_paise("unknownword hazaar") is None
