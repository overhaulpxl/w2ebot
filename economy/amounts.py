import re

from .constants import ECONOMY_MAX_AMOUNT


class AmountParseError(ValueError):
    pass


_DIGITS = re.compile(r"^[0-9]+$")
_GROUPED = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{3})+$")
_SUFFIXED = re.compile(r"^([0-9]+)([km])$", re.IGNORECASE)


def _validate_amount(amount, *, allow_zero):
    if amount < 0 or (amount == 0 and not allow_zero):
        raise AmountParseError("Jumlah harus lebih dari nol.")
    if amount > ECONOMY_MAX_AMOUNT:
        raise AmountParseError("Jumlah melebihi batas ekonomi.")
    return amount


def parse_economy_amount(value, *, balance=None, allow_all=False, allow_half=False, allow_zero=False):
    if value is None or isinstance(value, bool):
        raise AmountParseError("Jumlah tidak valid.")
    if isinstance(value, int):
        return _validate_amount(value, allow_zero=allow_zero)
    if not isinstance(value, str):
        raise AmountParseError("Jumlah harus berupa bilangan bulat.")

    text = value.strip().lower()
    if not text or any(ch.isspace() for ch in text):
        raise AmountParseError("Jumlah tidak valid.")
    if text == "all":
        if not allow_all or balance is None:
            raise AmountParseError("Opsi all tidak tersedia.")
        return _validate_amount(_coerce_balance(balance), allow_zero=allow_zero)
    if text == "half":
        if not allow_half or balance is None:
            raise AmountParseError("Opsi half tidak tersedia.")
        return _validate_amount(_coerce_balance(balance) // 2, allow_zero=allow_zero)

    if _DIGITS.fullmatch(text):
        amount = int(text)
    elif _GROUPED.fullmatch(text):
        amount = int(text.replace(".", ""))
    else:
        match = _SUFFIXED.fullmatch(text)
        if not match:
            raise AmountParseError("Format jumlah tidak didukung.")
        multiplier = 1_000 if match.group(2).lower() == "k" else 1_000_000
        amount = int(match.group(1)) * multiplier
    return _validate_amount(amount, allow_zero=allow_zero)


def _coerce_balance(balance):
    if isinstance(balance, bool) or not isinstance(balance, int):
        raise AmountParseError("Saldo konteks tidak valid.")
    return balance


def format_economy_amount(amount, currency):
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("amount must be an integer")
    currency = str(currency).upper()
    if currency not in ("ETM", "ECY"):
        raise ValueError("unsupported currency")
    return f"{amount:,}".replace(",", ".") + f" {currency}"


def allocate_basis_points(amount, allocations):
    """Allocate an integer amount exactly using ordered basis-point weights."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise AmountParseError("Jumlah alokasi tidak valid.")
    if not allocations or sum(weight for _, weight in allocations) != 10_000:
        raise ValueError("basis-point allocations must total 10000")
    result = []
    assigned = 0
    for index, (name, weight) in enumerate(allocations):
        share = amount - assigned if index == len(allocations) - 1 else amount * weight // 10_000
        result.append((name, share))
        assigned += share
    return result
