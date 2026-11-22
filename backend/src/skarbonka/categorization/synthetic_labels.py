"""Synthetic labelled transactions for training and testing the classifier (M6).

Every merchant is invented: a shop-type stem ("PIEKARNIA", "STACJA PALIW") plus an invented
name and a city. Each category gets many distinct merchants, so a split grouped by merchant
still leaves every category on both sides. Reproducible for a given seed.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from skarbonka.categorization.rules import TransactionView

# category path -> (shop-type stems, min grosze, max grosze)
CATEGORY_STEMS: dict[str, tuple[tuple[str, ...], int, int]] = {
    "Jedzenie/Zakupy spożywcze": (
        (
            "DELIKATESY",
            "SKLEP SPOŻYWCZY",
            "MARKET",
            "SUPERSAM",
            "WARZYWNIAK",
            "MINI MARKET",
            "HALA TARGOWA",
            "SPOŻYWCZY",
        ),
        1500,
        25000,
    ),
    "Jedzenie/Przekąski": (
        ("KIOSK", "CUKIERNIA", "LODZIARNIA", "PIEKARNIA", "AUTOMAT VENDING", "SŁODYCZE"),
        300,
        3500,
    ),
    "Jedzenie/Restauracje": (
        ("RESTAURACJA", "PIZZERIA", "BISTRO", "KEBAB", "SUSHI BAR", "BAR MLECZNY", "TRATTORIA"),
        2500,
        18000,
    ),
    "Dom/Chemia i higiena": (
        ("DROGERIA", "PERFUMERIA", "CHEMIA GOSPODARCZA", "KOSMETYKI"),
        800,
        12000,
    ),
    "Dom/Meble i wyposażenie": (
        ("MEBLE", "SALON MEBLOWY", "DOM I WNĘTRZE", "TEKSTYLIA DOMOWE", "OŚWIETLENIE"),
        3000,
        150000,
    ),
    "Transport/Paliwo": (
        ("STACJA PALIW", "PALIWA", "AUTO GAZ", "PETROL", "TANKSTELLE"),
        8000,
        35000,
    ),
    "Transport/Komunikacja": (
        ("BILET MIEJSKI", "KOMUNIKACJA MIEJSKA", "PRZEWOZY REGIONALNE", "PARKING", "TAXI"),
        340,
        6000,
    ),
    "Zdrowie/Apteka": (
        ("APTEKA", "PUNKT APTECZNY", "APTEKA RODZINNA", "FARMACJA"),
        900,
        15000,
    ),
    "Sport/Siłownia": (
        ("FITNESS", "SIŁOWNIA", "KLUB SPORTOWY", "CROSSFIT", "BASEN"),
        2000,
        16000,
    ),
}

NAMES = (
    "U HANI",
    "POD LIPAMI",
    "CENTRUM",
    "SMAK",
    "ZOSIA",
    "NOVA",
    "BOREK",
    "ŚLĄSK",
    "MAJA",
    "ZŁOTY RÓG",
    "PIAST",
    "KOLOROWA",
    "WIOSNA",
    "PRZY RYNKU",
    "AGATKA",
    "BRACIA K",
    "OAZA",
    "EXPRESS",
    "GÓRNIK",
    "ZIELONA",
    "PLUS",
    "DOBRA",
    "STOKOWA",
    "LAS",
    "MOST",
)
CITIES = ("KATOWICE", "GLIWICE", "ZABRZE", "BYTOM", "CHORZÓW", "TYCHY")
ACCOUNTS = ("Konto Direct", "Konto Oszczędnościowe")


@dataclass(frozen=True)
class LabelledExample:
    view: TransactionView
    label: str
    merchant: str


def synthetic_examples(
    seed: int = 0, merchants_per_category: int = 14, purchases_per_merchant: int = 6
) -> list[LabelledExample]:
    """Labelled card purchases from invented merchants, several per merchant."""
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security
    start = date(2026, 1, 1)
    examples: list[LabelledExample] = []
    for label, (stems, low, high) in CATEGORY_STEMS.items():
        seen: set[str] = set()
        while len(seen) < merchants_per_category:
            merchant = f"{rng.choice(stems)} {rng.choice(NAMES)}"
            if merchant in seen:
                continue
            seen.add(merchant)
            city = rng.choice(CITIES)
            store = rng.randint(1, 999)
            for _ in range(purchases_per_merchant):
                day = start + timedelta(days=rng.randint(0, 300))
                amount = -(Decimal(rng.randint(low, high)) / 100).quantize(Decimal("0.01"))
                counterparty = f" {merchant} {store}  {city}  POL "
                card = rng.randint(0, 9999)
                view = TransactionView(
                    counterparty=counterparty,
                    title=f" Płatność kartą {day:%d.%m.%Y} Nr karty 4246xx{card:04d}",
                    amount=amount,
                    account=rng.choice(ACCOUNTS),
                    transaction_date=day,
                    operation_kind="card",
                    merchant=None,
                )
                examples.append(LabelledExample(view, label, merchant))
    return examples
