"""Unit tests for number normalization in Hindi, Hinglish, English, and Devanagari."""

from app.nlu.numbers import extract_number, normalize_amount_paise


def test_arabic_digits() -> None:
    assert normalize_amount_paise("340") == 34000
    assert normalize_amount_paise("500") == 50000
    assert normalize_amount_paise("1250") == 125000


def test_devanagari_digits() -> None:
    assert normalize_amount_paise("३४०") == 34000
    assert normalize_amount_paise("५००") == 50000
    assert normalize_amount_paise("१२५०") == 125000


def test_english_words() -> None:
    assert normalize_amount_paise("three hundred forty") == 34000
    assert normalize_amount_paise("five hundred") == 50000
    assert normalize_amount_paise("two thousand five hundred") == 250000


def test_hindi_hinglish_words() -> None:
    assert normalize_amount_paise("teen sau chaalis") == 34000
    assert normalize_amount_paise("paanch sau") == 50000
    assert normalize_amount_paise("do hazaar paanch sau") == 250000
    assert normalize_amount_paise("aath sau") == 80000
    assert normalize_amount_paise("barah sau pachaas") == 125000


def test_hindi_devanagari_words() -> None:
    assert normalize_amount_paise("तीन सौ चालीस") == 34000
    assert normalize_amount_paise("पाँच सौ") == 50000
    assert normalize_amount_paise("बारह सौ पचास") == 125000


def test_fractions() -> None:
    # dedh sau = 150
    assert normalize_amount_paise("dedh sau") == 15000
    # dhai sau = 250
    assert normalize_amount_paise("dhai sau") == 25000
    # dhai hazaar = 2500
    assert normalize_amount_paise("dhai hazaar") == 250000
    # sawa sau = 125
    assert normalize_amount_paise("sava sau") == 12500
    assert normalize_amount_paise("sawa sau") == 12500
    # saadhe teen sau = 350
    assert normalize_amount_paise("saadhe teen sau") == 35000
    assert normalize_amount_paise("साढ़े तीन सौ") == 35000
    # paune teen sau = 275
    assert normalize_amount_paise("paune teen sau") == 27500


def test_code_mixed_numbers() -> None:
    assert normalize_amount_paise("teen sau 40") == 34000
    assert normalize_amount_paise("2 hazaar 500") == 250000


def test_verb_likh_do_not_number_two() -> None:
    # "likh do" should not extract 2
    res = extract_number("Ramesh ka 340 likh do")
    assert res is not None
    amount, consumed_tokens = res
    assert amount == 34000


def test_unknown_number_token_fails_completely() -> None:
    # Unknown word mixed with number tokens must return None, NOT partial amount
    # e.g. "chaarxyz sau" should fail, not parse as 100
    assert normalize_amount_paise("unknownword sau") is None
