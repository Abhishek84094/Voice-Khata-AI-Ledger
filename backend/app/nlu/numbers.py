"""High-precision number normalizer for Hindi, Hinglish, English, and Devanagari.

Rules:
1. Returns integer paise or None on failure / ambiguous tokens.
2. NEVER returns a partial number if an unknown number word is present.
3. Disambiguates verbal 'do' ('likh do', 'kar do') from numeral 2 ('do').
4. Handles fractions: dedh, dhai, sawa, saadhe, paune.
5. Handles Devanagari digits: ०-९.
"""

from __future__ import annotations

DEVANAGARI_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}

# 1 to 99 in Hindi (transliterated and Devanagari) and English
UNITS_AND_TEENS: dict[str, int] = {
    # English
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    # Hindi 1-10
    "ek": 1,
    "ekk": 1,
    "एक": 1,
    "do": 2,
    "दो": 2,
    "teen": 3,
    "tin": 3,
    "तीन": 3,
    "char": 4,
    "chaar": 4,
    "चार": 4,
    "panch": 5,
    "paanch": 5,
    "पाँच": 5,
    "पांच": 5,
    "chhah": 6,
    "chhe": 6,
    "che": 6,
    "छह": 6,
    "छः": 6,
    "saat": 7,
    "sat": 7,
    "सात": 7,
    "aath": 8,
    "ath": 8,
    "आठ": 8,
    "nau": 9,
    "nav": 9,
    "नौ": 9,
    "das": 10,
    "dass": 10,
    "दस": 10,
    # Hindi 11-20
    "gyarah": 11,
    "gyara": 11,
    "ग्यारह": 11,
    "barah": 12,
    "bara": 12,
    "बारह": 12,
    "terah": 13,
    "tera": 13,
    "तेरह": 13,
    "chaudah": 14,
    "chauda": 14,
    "चौदह": 14,
    "pandrah": 15,
    "pandra": 15,
    "पंद्रह": 15,
    "solah": 16,
    "sola": 16,
    "सोलह": 16,
    "satrah": 17,
    "satra": 17,
    "सत्रह": 17,
    "atharah": 18,
    "athara": 18,
    "अठारह": 18,
    "unnis": 19,
    "unnees": 19,
    "उन्नीस": 19,
    "bees": 20,
    "bis": 20,
    "बीस": 20,
    # Hindi 21-30
    "ikkis": 21,
    "इक्कीस": 21,
    "baais": 22,
    "बाईस": 22,
    "teis": 23,
    "तेईस": 23,
    "chaubis": 24,
    "चौबीस": 24,
    "pachchis": 25,
    "पच्चीस": 25,
    "chhabis": 26,
    "छब्बीस": 26,
    "sattais": 27,
    "सत्ताईस": 27,
    "athhais": 28,
    "अट्ठाईस": 28,
    "unatis": 29,
    "untees": 29,
    "उनतीस": 29,
    "tees": 30,
    "तीस": 30,
    # Hindi 31-40
    "iktis": 31,
    "इकत्तीस": 31,
    "battis": 32,
    "बत्तीस": 32,
    "tetis": 33,
    "तैंतीस": 33,
    "chauntis": 34,
    "चौंतीस": 34,
    "paintis": 35,
    "पैंतीस": 35,
    "chhattis": 36,
    "छत्तीस": 36,
    "saintis": 37,
    "सैंतीस": 37,
    "adhtis": 38,
    "अड़तीस": 38,
    "untalis": 39,
    "उनतालीस": 39,
    "chalis": 40,
    "chaalis": 40,
    "चालीस": 40,
    # Hindi 41-50
    "iktalis": 41,
    "इकतालीस": 41,
    "bayalis": 42,
    "बयालीस": 42,
    "taitalis": 43,
    "तैंतालीस": 43,
    "chauwalis": 44,
    "चवालीस": 44,
    "paintalis": 45,
    "पैंतालीस": 45,
    "chhiyalis": 46,
    "छियालीस": 46,
    "saintalis": 47,
    "सैंतालीस": 47,
    "adtalis": 48,
    "अड़तालीस": 48,
    "unchas": 49,
    "उनचास": 49,
    "pachas": 50,
    "pachaas": 50,
    "पचास": 50,
    # Hindi 51-60
    "ikyawan": 51,
    "इक्यावन": 51,
    "bawan": 52,
    "बावन": 52,
    "tirepan": 53,
    "तिरेपन": 53,
    "chauwan": 54,
    "चौवन": 54,
    "pachpan": 55,
    "पचपन": 55,
    "chhappan": 56,
    "छप्पन": 56,
    "sattawan": 57,
    "सत्तावन": 57,
    "athawan": 58,
    "अट्ठावन": 58,
    "unsath": 59,
    "उनसठ": 59,
    "saath": 60,
    "sath": 60,
    "साठ": 60,
    # Hindi 61-70
    "iksath": 61,
    "इकसठ": 61,
    "basath": 62,
    "बासठ": 62,
    "tirsath": 63,
    "तिरसठ": 63,
    "chaunsath": 64,
    "चौंसठ": 64,
    "painsath": 65,
    "पैंसठ": 65,
    "chhiyashath": 66,
    "छियासठ": 66,
    "sadsath": 67,
    "सरसठ": 67,
    "athsath": 68,
    "अड़सठ": 68,
    "unhattar": 69,
    "उनहत्तर": 69,
    "sattar": 70,
    "सत्तर": 70,
    # Hindi 71-80
    "ikhattar": 71,
    "इकहत्तर": 71,
    "bahattar": 72,
    "बहत्तर": 72,
    "tihattar": 73,
    "तिहत्तर": 73,
    "chauhattar": 74,
    "चौहत्तर": 74,
    "pachhattar": 75,
    "पचहत्तर": 75,
    "chhihattar": 76,
    "छिहत्तर": 76,
    "satattar": 77,
    "सतहत्तर": 77,
    "athhattar": 78,
    "अठहत्तर": 78,
    "unasi": 79,
    "उनासी": 79,
    "assi": 80,
    "अस्सी": 80,
    # Hindi 81-90
    "ikyasi": 81,
    "इक्यासी": 81,
    "bayasi": 82,
    "बयासी": 82,
    "tirasi": 83,
    "तिरासी": 83,
    "chaurasi": 84,
    "चौरासी": 84,
    "pachasi": 85,
    "पचासी": 85,
    "chhiyasi": 86,
    "छियासी": 86,
    "sattasi": 87,
    "सतासी": 87,
    "athasi": 88,
    "अठासी": 88,
    "nawasi": 89,
    "नवासी": 89,
    "nabbe": 90,
    "नब्बे": 90,
    # Hindi 91-99
    "ikyanwe": 91,
    "इक्यानवे": 91,
    "banwe": 92,
    "बानवे": 92,
    "tiranwe": 93,
    "तिरानवे": 93,
    "chauranwe": 94,
    "चौरानवे": 94,
    "pachanwe": 95,
    "पचानवे": 95,
    "chhiyanwe": 96,
    "छियानवे": 96,
    "sattanwe": 97,
    "सत्तानवे": 97,
    "athanwe": 98,
    "अट्ठानवे": 98,
    "ninyanwe": 99,
    "निन्यानवे": 99,
}

SCALES: dict[str, int] = {
    "sau": 100,
    "hundred": 100,
    "सौ": 100,
    "hazaar": 1000,
    "hazar": 1000,
    "thousand": 1000,
    "हज़ार": 1000,
    "हजार": 1000,
    "k": 1000,
    "lakh": 100000,
    "lac": 100000,
    "लाख": 100000,
    "crore": 10000000,
    "करोड़": 10000000,
}

FRACTION_PREFIXES: dict[str, float] = {
    "dedh": 1.5,
    "डेढ़": 1.5,
    "dhai": 2.5,
    "dhayi": 2.5,
    "ढाई": 2.5,
    "sawa": 0.25,
    "sava": 0.25,
    "सवा": 0.25,
    "saadhe": 0.5,
    "sadhe": 0.5,
    "साढ़े": 0.5,
    "paune": -0.25,
    "पौने": -0.25,
}

VERBAL_DO_PRECEDING = {
    "likh",
    "kar",
    "hata",
    "de",
    "bata",
    "bhej",
    "daal",
    "लिख",
    "कर",
    "हटा",
    "दे",
    "बता",
    "भेज",
    "डाल",
}


def devanagari_to_arabic_digits(text: str) -> str:
    """Replace Devanagari numerals ०-९ with standard Arabic digits 0-9."""
    for dev, arab in DEVANAGARI_DIGITS.items():
        text = text.replace(dev, arab)
    return text


def clean_number_token(token: str) -> str:
    """Normalize token by stripping currency symbols and punctuation."""
    token = token.strip("₹$,.।!?")
    token = devanagari_to_arabic_digits(token)
    return token.lower()


def parse_spoken_number(tokens: list[str]) -> tuple[int | None, int]:
    """Parse a sequence of number words/digits starting at tokens[0].

    Returns (value, consumed_token_count).
    If tokens contain invalid or contradictory number parts, returns (None, 0).
    """
    if not tokens:
        return None, 0

    idx = 0
    total = 0
    current_unit: int | None = None
    fraction_op: tuple[str, float] | None = None
    consumed = 0

    while idx < len(tokens):
        raw = tokens[idx]
        t = clean_number_token(raw)

        # Check verbal 'do' check
        if (
            t in ("do", "दो")
            and idx > 0
            and clean_number_token(tokens[idx - 1]) in VERBAL_DO_PRECEDING
        ):
            break

        # Check pure digits
        if t.isascii() and t.isdigit():
            val = int(t)
            consumed += 1
            idx += 1
            # Check if followed by scale like 'hazaar' or 'sau'
            if idx < len(tokens) and clean_number_token(tokens[idx]) in SCALES:
                scale_val = SCALES[clean_number_token(tokens[idx])]
                total += val * scale_val
                consumed += 1
                idx += 1
                current_unit = None
            else:
                if current_unit is not None:
                    # e.g. "two thousand 500"
                    total += current_unit + val
                    current_unit = None
                else:
                    current_unit = val
            continue

        # Check fractions
        if t in FRACTION_PREFIXES:
            fraction_op = (t, FRACTION_PREFIXES[t])
            consumed += 1
            idx += 1

            # Check what follows fraction
            if idx < len(tokens):
                next_t = clean_number_token(tokens[idx])
                # dedh sau / dedh hazaar
                if fraction_op[0] in ("dedh", "डेढ़", "dhai", "dhayi", "ढाई"):
                    if next_t in SCALES:
                        total += int(fraction_op[1] * SCALES[next_t])
                        consumed += 1
                        idx += 1
                        fraction_op = None
                        current_unit = None
                        continue
                    else:
                        # "dedh" alone usually means 150 (dedh sau) or 1.5
                        total += int(fraction_op[1] * 100)
                        fraction_op = None
                        continue

                # saadhe teen sau / paune teen sau / sawa do hazaar
                if next_t in UNITS_AND_TEENS:
                    base_unit = UNITS_AND_TEENS[next_t]
                    consumed += 1
                    idx += 1
                    if idx < len(tokens) and clean_number_token(tokens[idx]) in SCALES:
                        scale = SCALES[clean_number_token(tokens[idx])]
                        consumed += 1
                        idx += 1
                        if fraction_op[0] in ("saadhe", "sadhe", "साढ़े"):
                            total += int((base_unit + 0.5) * scale)
                        elif fraction_op[0] in ("sawa", "sava", "सवा"):
                            total += int((base_unit + 0.25) * scale)
                        elif fraction_op[0] in ("paune", "पौने"):
                            total += int((base_unit - 0.25) * scale)
                        fraction_op = None
                        current_unit = None
                        continue
                    else:
                        # e.g. saadhe teen = 3.5 -> 350
                        if fraction_op[0] in ("saadhe", "sadhe", "साढ़े"):
                            total += int((base_unit + 0.5) * 100)
                        elif fraction_op[0] in ("sawa", "sava", "सवा"):
                            total += int((base_unit + 0.25) * 100)
                        elif fraction_op[0] in ("paune", "पौने"):
                            total += int((base_unit - 0.25) * 100)
                        fraction_op = None
                        current_unit = None
                        continue
                elif next_t in SCALES:
                    # sawa sau = 125, paune sau = 75
                    scale = SCALES[next_t]
                    consumed += 1
                    idx += 1
                    if fraction_op[0] in ("sawa", "sava", "सवा"):
                        total += int(1.25 * scale)
                    elif fraction_op[0] in ("paune", "पौने"):
                        total += int(0.75 * scale)
                    fraction_op = None
                    continue

        # Check basic units/teens/tens
        if t in UNITS_AND_TEENS:
            val = UNITS_AND_TEENS[t]
            consumed += 1
            idx += 1
            if current_unit is not None:
                # e.g. "twenty five"
                if current_unit < 100 and val < 10:
                    current_unit += val
                else:
                    total += current_unit
                    current_unit = val
            else:
                current_unit = val
            continue

        # Check scales (sau, hazaar, lakh)
        if t in SCALES:
            scale = SCALES[t]
            consumed += 1
            idx += 1
            mult = current_unit if current_unit is not None else 1
            total += mult * scale
            current_unit = None
            continue

        # Non-number token encountered, end number parse
        break

    if current_unit is not None:
        total += current_unit

    if consumed > 0 and total > 0:
        return total, consumed
    return None, 0


def extract_number(text: str) -> tuple[int, list[str]] | None:
    """Find and normalize the first valid currency amount in text.

    Returns (amount_paise, consumed_tokens) or None if not found/invalid.
    """
    raw_tokens = text.split()
    for i in range(len(raw_tokens)):
        val, count = parse_spoken_number(raw_tokens[i:])
        if val is not None and count > 0:
            return val * 100, raw_tokens[i : i + count]
    return None


def normalize_amount_paise(text: str) -> int | None:
    """Extract full currency amount in integer paise.

    If any unrecognised token appears in a number sequence, returns None.
    """
    # Guard against unknown words mixed in number strings like "unknownword sau"
    tokens = text.split()
    # Check if text contains number words or digits
    for i in range(len(tokens)):
        t = clean_number_token(tokens[i])
        if t in SCALES and i > 0:
            prev = clean_number_token(tokens[i - 1])
            if (
                not (prev.isascii() and prev.isdigit())
                and prev not in UNITS_AND_TEENS
                and prev not in FRACTION_PREFIXES
                and prev not in ("ka", "ko", "ne", "ek")
            ):
                return None

    res = extract_number(text)
    if res is not None:
        return res[0]
    return None
