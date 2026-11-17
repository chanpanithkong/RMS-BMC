"""Decimal money helpers (BR-033). Never use float for money."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")
INTERNAL = Decimal("0.0001")

MINOR_UNITS = {"USD": CENT, "KHR": Decimal("1")}


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError("float is not allowed for money; pass a string or Decimal")
    return Decimal(str(value))


def q(value: Decimal, currency: str = "USD") -> Decimal:
    """Round half-up to the currency minor unit."""
    return D(value).quantize(MINOR_UNITS.get(currency, CENT), rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    return D(value).quantize(INTERNAL, rounding=ROUND_HALF_UP)


def round_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    """Cash rounding, e.g. KHR to the nearest 100 riel."""
    if increment <= 0:
        raise ValueError("rounding increment must be positive")
    return (D(value) / increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * increment
