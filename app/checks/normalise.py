"""Value extractors for Type B checks. Every one isolates its span first.

Ported from reference/spike/normalise.py, carrying forward the span-isolation
fix (D14 bug 1): a targeted regex finds the value's span BEFORE normalising,
never find-and-replace across the whole utterance. An earlier spike version
normalised the entire utterance and picked up leading words like "and your
email is" as part of the address. The same principle is applied here to money,
dates and street addresses, not just email.
"""

from __future__ import annotations

import re

_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def words_to_number(phrase: str) -> float | None:
    """'forty two point nine' -> 42.9, 'twenty five' -> 25. None if it can't parse."""
    phrase = phrase.lower().strip()
    if "point" in phrase:
        whole, _, frac = phrase.partition("point")
        w = words_to_number(whole)
        f = words_to_number(frac)
        if w is None or f is None:
            return None
        return float(f"{int(w)}.{int(f)}")
    tokens = re.findall(r"[a-z]+", phrase)
    total = 0
    matched = False
    for tok in tokens:
        if tok in _WORDS:
            total += _WORDS[tok]
            matched = True
    return float(total) if matched else None


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

# Digit form: "$42.90", "79.90 dollars", "$79.90 a month", "$42 and 90". Either
# the $ sign or the word "dollars" marks it as money. The trailing cents can be
# a decimal ("$42.90"), or spoken out as "and 90" with no "cents" word at all:
# Deepgram's smart_format sometimes renders "forty two dollars and ninety" as
# "$42 and 90" rather than "$42.90" when it never heard the word "cents".
# "and 90" after a bare dollar figure is accepted as cents on that basis alone.
_MONEY_DIGIT_SPAN = re.compile(
    r"(?:\$\s*(\d+(?:\.\d{1,2})?)|(\d+(?:\.\d{1,2})?)\s*dollars?)"
    r"(?:\s*and\s*(\d{1,2})\s*cents?\b|\s*and\s*(\d{1,2})\b|\s*(\d{1,2})\s*cents?\b)?"
)

# Spoken form: "forty two dollars and ninety", "seventy nine ninety". Word
# counts are bounded ({1,4}, {1,3}) rather than unbounded (+), which keeps the
# match linear: an unbounded nested quantifier against long non-matching agent
# speech (most turns say no money at all) caused catastrophic backtracking and
# hung the whole scoring pass. No real quoted price needs more than a few words.
# Longest alternatives first: regex alternation is first-match-wins, not
# longest-match, so "nine" ahead of "ninety" would match only the first four
# letters of "ninety" and silently drop the rest of the word (42.09 instead
# of 42.90). \b word boundaries are the second half of the same fix.
_NUMBER_WORD = (
    r"\b(?:seventeen|eighteen|nineteen|thirteen|fourteen|fifteen|sixteen|"
    r"seventy|eighty|ninety|twelve|eleven|thirty|forty|fifty|sixty|twenty|"
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten)\b"
)
_MONEY_WORD_SPAN = re.compile(
    rf"((?:{_NUMBER_WORD}[\s-]?){{1,4}})\s*dollars?\s*(?:and\s*)?"
    rf"((?:{_NUMBER_WORD}[\s-]?){{1,3}})?(?:\s*cents?)?"
)


# Words near a price that mark it as the promo (first N months) figure or the
# ongoing (after that) figure. A single call quotes both prices, often in the
# same turn, so the bare number alone cannot tell promo from ongoing; nearby
# text is the only signal available.
_PROMO_MARKERS = ("first", "for six", "for the first", "promo", "promotional")
_ONGOING_MARKERS = (
    "after that", "ongoing", "regular", "standard", "then it goes", "then seventy", "goes to",
)

_WORDS_OF_CONTEXT = 6


def _role_near(text: str, start: int, end: int) -> str:
    """promo | ongoing | unknown, from words either side of a price mention.

    "then $79.90 ongoing" carries its marker after the figure; "$42.90 for six
    months" carries it after too; "for the first six months, it's $42.90"
    carries it before. Both sides are checked, but each stops at the nearest
    sentence boundary, so a marker that belongs to the *next* sentence (as in
    "...$42.90 a month. After that, it goes to $79.90") is never pulled onto
    this mention.
    """
    before_stop = max((text.rfind(p, 0, start) for p in ".!?"), default=-1)
    before = text[max(before_stop + 1, start - 40) : start]

    after_stop = min((p for p in (text.find(c, end) for c in ".!?") if p != -1), default=len(text))
    after = text[end : min(after_stop, end + 25)]

    for marker in _ONGOING_MARKERS:
        if marker in before or marker in after:
            return "ongoing"
    for marker in _PROMO_MARKERS:
        if marker in before or marker in after:
            return "promo"
    return "unknown"


def extract_money_mentions(text: str) -> list[tuple[float, str]]:
    """Every dollar amount mentioned in this text, as (value, role).

    role is "promo", "ongoing" or "unknown", read from nearby words such as
    "for the first six months" or "after that". A call quotes both prices, so
    the bare figure alone cannot say which field it belongs to.

    Isolates each money span with its own regex before parsing it, rather than
    scanning the whole utterance for stray digits, so "6 months" or "25 Mbps"
    never get mistaken for a price (D14 span-isolation rule, extended past email).
    """
    text = text.lower()
    values: list[tuple[float, str]] = []

    for match in _MONEY_DIGIT_SPAN.finditer(text):
        dollar_sign_form, word_form, and_cents, and_bare, cents_word = match.groups()
        dollars_str = dollar_sign_form or word_form
        dollars = float(dollars_str)
        cents_str = and_cents or and_bare or cents_word
        if cents_str and "." not in dollars_str:
            dollars += int(cents_str) / 100
        values.append((round(dollars, 2), _role_near(text, match.start(), match.end())))

    if values:
        return values

    for match in _MONEY_WORD_SPAN.finditer(text):
        dollars_words, cents_words = match.groups()
        dollars = words_to_number(dollars_words)
        if dollars is None:
            continue
        cents = words_to_number(cents_words) if cents_words else 0.0
        cents = cents or 0.0
        role = _role_near(text, match.start(), match.end())
        values.append((round(dollars + cents / 100, 2), role))

    return values


# ---------------------------------------------------------------------------
# Promo term and download speed
# ---------------------------------------------------------------------------

_TERM_SPAN = re.compile(rf"(?:for the first|for)\s+((?:{_NUMBER_WORD}[\s-]?){{1,3}})\s+months?\b")


def extract_promo_term_months(text: str) -> int | None:
    """'for the first six months' -> 6."""
    text = text.lower()
    for match in _TERM_SPAN.finditer(text):
        value = words_to_number(match.group(1))
        if value is not None:
            return int(value)
    return None


_SPEED_SPAN = re.compile(
    rf"((?:{_NUMBER_WORD}[\s-]?){{1,3}}|\d+(?:\.\d+)?)\s*"
    r"(?:mbps|megabits?(?:\s+per\s+second)?|megabytes?(?:\s+per\s+second)?)"
)


def extract_download_speed_mbps(text: str) -> float | None:
    """'twenty five Mbps' or '25 megabits per second' -> 25.0.

    Deepgram sometimes mishears "megabits" as "megabytes"; both are accepted
    here since the unit word itself is not what this check compares.
    """
    text = text.lower()
    match = _SPEED_SPAN.search(text)
    if not match:
        return None
    raw = match.group(1).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    return words_to_number(raw)


# ---------------------------------------------------------------------------
# Modem model
# ---------------------------------------------------------------------------

# "netcomm cf40" is often mangled by STT as "netcom c f 40" or "netcom p s
# forty" (spike note); the letters and the model number are matched loosely.
_MODEM_SPAN = re.compile(r"net\s*com[m]?\s*(?:c\s*f|p\s*s)?\s*[- ]?\s*(\d{2,3})\b", re.IGNORECASE)


def extract_modem_model(text: str) -> str | None:
    """'Netcomm CF40' / 'Netcom CF 40' / 'Netcom p s forty' -> 'Netcomm CF40'.

    Isolates the brand-plus-model span first; STT commonly mangles this name
    (spike note), so the number is what is trusted, not the exact letters.
    """
    match = _MODEM_SPAN.search(text)
    if match:
        return f"Netcomm CF{match.group(1)}"
    # Spoken model number as words: "netcom cf forty"
    m2 = re.search(r"net\s*com[m]?\s*(?:cf|p\s*s)?\s*([a-z]+)\b", text.lower())
    if m2:
        num = words_to_number(m2.group(1))
        if num is not None:
            return f"Netcomm CF{int(num)}"
    return None


# ---------------------------------------------------------------------------
# Email (D14 bug 1: the original span-isolation fix)
# ---------------------------------------------------------------------------

_EMAIL_SPAN = re.compile(
    r"([a-z0-9]+(?:\s+dot\s+[a-z0-9]+)*)\s+at\s+([a-z0-9]+(?:\s+dot\s+[a-z0-9]+)*)\s+dot\s+([a-z]{2,})"
)
_EMAIL_LITERAL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")


def extract_spoken_email(text: str) -> str | None:
    """Finds the email SPAN inside a longer sentence, not the whole utterance.

    'I have it as j dot avery at example dot com' -> 'j.avery@example.com'.
    Also accepts a literal address if Deepgram's smart_format already wrote one
    ('j.avery@example.com'), which is what nova-3 actually returns on the
    real call rather than spelling out "dot" and "at".
    """
    text = text.lower().strip()
    literal = _EMAIL_LITERAL.search(text)
    if literal:
        return literal.group(0)
    m = _EMAIL_SPAN.search(text)
    if not m:
        return None
    local, domain, tld = m.groups()
    local = local.replace(" dot ", ".").replace(" ", "")
    domain = domain.replace(" dot ", ".").replace(" ", "")
    return f"{local}@{domain}.{tld}"


# ---------------------------------------------------------------------------
# Date of birth
# ---------------------------------------------------------------------------

_DATE_NUMERIC_SPAN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

_ORDINAL_WORD = (
    r"(?:twenty[\s-]?)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
    r"nineteenth|twentieth|thirtieth)"
)
_MONTH_WORD = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
)

_DATE_SPOKEN_SPAN = re.compile(
    rf"\b({_ORDINAL_WORD})\s+of\s+({_MONTH_WORD})[,\s]+((?:nineteen|twenty)\s+[a-z\s-]+?)(?=[.,!?]|$)",
    re.IGNORECASE,
)

_ORDINAL_DAY = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "thirtieth": 30,
}


def _spoken_year_to_number(phrase: str) -> int | None:
    """'nineteen ninety' -> 1990, 'twenty ten' -> 2010."""
    tokens = phrase.lower().split()
    if not tokens:
        return None
    if tokens[0] == "nineteen":
        rest = words_to_number(" ".join(tokens[1:])) or 0
        return 1900 + int(rest)
    if tokens[0] == "twenty":
        rest = words_to_number(" ".join(tokens[1:])) or 0
        return 2000 + int(rest)
    value = words_to_number(phrase)
    return int(value) if value else None


def extract_dob(text: str) -> str | None:
    """Isolated DOB span -> ISO 'YYYY-MM-DD'.

    Numeric dates default day-first (en-AU), and read month-first only when the
    first number exceeds 12, since that is the one case unambiguous either way.
    Deepgram writes the spoken "fourteenth of March, nineteen ninety" as the
    numeric '03/14/1990' (US order) on this call, so both paths must agree on
    the same date.
    """
    text = text.lower().strip()

    m = _DATE_NUMERIC_SPAN.search(text)
    if m:
        a, b, year = (int(g) for g in m.groups())
        if year < 100:
            year += 1900 if year > 30 else 2000
        if a > 12:
            # Unambiguous: a cannot be a month, so it must be month-first
            # order read backwards, i.e. a is the day. This branch only fires
            # when b <= 12, so (day=a, month=b) is the only valid reading.
            day, month = a, b
        elif b > 12:
            # Mirror case: b cannot be a month, so a must be the month. This is
            # Deepgram's numeric DOB on the demo call: '03/14/1990' is US
            # month/day order for 14 March, so a=month, b=day.
            day, month = b, a
        else:
            # Both <= 12: genuinely ambiguous between day-first and
            # month-first. Default day-first (en-AU), per D19.
            day, month = a, b
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    m2 = _DATE_SPOKEN_SPAN.search(text)
    if m2:
        day_word, month_word, year_words = m2.groups()
        day_word = day_word.replace("twenty ", "").replace("twenty-", "").strip()
        day = _ORDINAL_DAY.get(day_word)
        if day is None and "twenty" in m2.group(1):
            base = _ORDINAL_DAY.get(day_word, 0)
            day = 20 + base if base else None
        month = _MONTHS.get(month_word)
        year = _spoken_year_to_number(year_words)
        if day and month and year:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


# ---------------------------------------------------------------------------
# Service address
# ---------------------------------------------------------------------------

_ADDRESS_SPAN = re.compile(
    r"\b(\d{1,5}\s+[a-z0-9'.\s]+?(?:street|st|road|rd|avenue|ave|drive|dr|place|pl|court|ct|"
    r"lane|ln)\b[a-z0-9,.\s]*?\b(\d{4})\b)",
    re.IGNORECASE,
)

_POSTCODE = re.compile(r"\b(\d{4})\b")
_STREET_NUMBER = re.compile(r"^\s*(\d{1,5})\b")

# The agent reads the state in full ("New South Wales"), the CRM stores the
# abbreviation ("NSW"). Both are normalised to the abbreviation before the
# fuzzy compare, or the two forms alone cost enough of the ratio to sit under
# threshold despite the address otherwise matching exactly.
_STATE_NAMES = {
    "new south wales": "nsw",
    "victoria": "vic",
    "queensland": "qld",
    "western australia": "wa",
    "south australia": "sa",
    "tasmania": "tas",
    "australian capital territory": "act",
    "northern territory": "nt",
}


def normalise_state_names(address: str) -> str:
    lowered = address.lower()
    for full, abbrev in _STATE_NAMES.items():
        lowered = lowered.replace(full, abbrev)
    return lowered


def extract_address_span(text: str) -> str | None:
    """Isolated street-address span, from the number through the postcode.

    Same span-isolation principle as email and money: matches the address
    substring specifically, so leading words like "the service address is"
    never enter the value that gets compared.
    """
    match = _ADDRESS_SPAN.search(text)
    return match.group(1).strip() if match else None


def address_parts(address: str) -> tuple[str | None, str | None]:
    """(street_number, postcode) from an address string, for the exact checks."""
    number_match = _STREET_NUMBER.match(address)
    postcode_match = _POSTCODE.search(address)
    return (
        number_match.group(1) if number_match else None,
        postcode_match.group(1) if postcode_match else None,
    )
