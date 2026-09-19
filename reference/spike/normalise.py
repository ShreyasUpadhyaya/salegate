import re

_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def words_to_number(phrase: str) -> float | None:
    """'twenty eight point six' -> 28.6. Returns None if it can't parse."""
    phrase = phrase.lower().strip()
    if "point" in phrase:
        whole, _, frac = phrase.partition("point")
        w = words_to_number(whole)
        f = words_to_number(frac)
        if w is None or f is None:
            return None
        return float(f"{int(w)}.{int(f)}")
    tokens = phrase.split()
    total = 0
    matched = False
    for tok in tokens:
        if tok in _WORDS:
            total += _WORDS[tok]
            matched = True
    return float(total) if matched else None


def extract_rate_c_per_kwh(text: str) -> float | None:
    """Find a cents-per-kWh rate near the word 'peak'. Handles digits or number words."""
    text = text.lower()
    # digit form: "28.6 cents"
    m = re.search(r"peak[^.]*?(\d+(?:\.\d+)?)\s*cents?", text)
    if m:
        return float(m.group(1))
    # spoken form: "peak is twenty eight point six cents"
    m = re.search(r"peak\s+is\s+([a-z\s]+?)\s+cents?", text)
    if m:
        return words_to_number(m.group(1))
    return None


_EMAIL_SPAN = re.compile(
    r"([a-z0-9]+(?:\s+dot\s+[a-z0-9]+)*)\s+at\s+([a-z0-9]+(?:\s+dot\s+[a-z0-9]+)*)\s+dot\s+([a-z]{2,})"
)


def normalise_spoken_email(text: str) -> str | None:
    """Finds the email SPAN inside a longer sentence, not the whole utterance.
    'and your email is j dot smith at gmail dot com' -> 'j.smith@gmail.com'.
    Bug caught in rehearsal: an earlier version normalised the entire utterance
    and picked up leading words like 'and your email is' as part of the address."""
    text = text.lower().strip()
    m = _EMAIL_SPAN.search(text)
    if not m:
        return None
    local, domain, tld = m.groups()
    local = local.replace(" dot ", ".").replace(" ", "")
    domain = domain.replace(" dot ", ".").replace(" ", "")
    return f"{local}@{domain}.{tld}"
