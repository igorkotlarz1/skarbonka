"""Merchant normalization. Pure functions over the ING counterparty field.

The field looks like " LIDL PANEWICKA  KATOWICE  POL ": name (with street) and city and
country, separated by double spaces. Not always: some merchants have no city or no country,
and payment processors add prefixes such as "BKG*", "PAYU*" or "SumUp *".
"""

import re
from dataclasses import dataclass

_FIELDS = re.compile(r"\s{2,}")
_COUNTRY = re.compile(r"[A-Z]{1,3}")
_PROCESSOR_PREFIX = re.compile(r"^[A-Za-z]{2,10}\s?\*\s*")
_HAS_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Counterparty:
    name: str
    city: str
    country: str


def parse_counterparty(raw: str) -> Counterparty:
    """Split into name, city and country. The country code goes only from the very end."""
    parts = [p for p in _FIELDS.split(raw.strip()) if p]
    if not parts:
        return Counterparty("", "", "")
    country = parts.pop() if len(parts) >= 2 and _COUNTRY.fullmatch(parts[-1]) else ""
    city = parts[1] if len(parts) >= 2 else ""
    name = _PROCESSOR_PREFIX.sub("", parts[0]).strip()
    return Counterparty(name, city, country)


def merchant_key(name: str) -> str:
    """Alias key: upper case, without tokens that hold digits (store numbers), single spaces."""
    tokens = [token for token in name.upper().split() if not _HAS_DIGIT.search(token)]
    return " ".join(tokens)


def contains_word(text: str, word: str) -> bool:
    """Case-insensitive whole-word match: "BP" is in "BP-PIAST" but not in "BPH" or "UBP"."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def best_keyword_match(name: str, merchants: dict[str, list[str]]) -> str | None:
    """The merchant whose longest keyword occurs in `name` as a whole word, if any."""
    best: tuple[int, str] | None = None
    for merchant, keywords in merchants.items():
        for keyword in keywords:
            if contains_word(name, keyword) and (best is None or len(keyword) > best[0]):
                best = (len(keyword), merchant)
    return best[1] if best else None


def display_name(key: str) -> str:
    """A readable merchant name for a new, unknown counterparty."""
    return key.title() if key else ""
