"""Validation and normalization for Polish business identifiers.

Checksums are verified locally so obviously-wrong identifiers fail fast without
a network round-trip. Only whitespace and common grouping separators (``-`` and
``.``) are tolerated in the input; any other character is rejected rather than
silently stripped, so ``"abc5261040828"`` is an error, not a valid NIP.
"""

from __future__ import annotations

import re
from datetime import date as Date, datetime
from zoneinfo import ZoneInfo

# Characters allowed purely as visual separators in a typed identifier.
_SEPARATORS = re.compile(r"[\s.\-]")
_ALL_DIGITS = re.compile(r"\A[0-9]+\Z")


def _clean(value: str) -> str:
    """Strip only whitespace/grouping separators; reject anything non-numeric."""
    if not isinstance(value, str):
        raise ValueError("identifier must be a string")
    stripped = _SEPARATORS.sub("", value)
    if not _ALL_DIGITS.match(stripped):
        raise ValueError(
            f"identifier may contain only digits and separators; got {value!r}"
        )
    return stripped


def _reject_all_zeros(digits: str, label: str) -> None:
    if set(digits) == {"0"}:
        raise ValueError(f"{label} {digits} is not a real identifier (all zeros)")


def normalize_nip(nip: str) -> str:
    """Return a clean 10-digit NIP, raising ValueError if it is invalid."""
    d = _clean(nip)
    if len(d) != 10:
        raise ValueError(f"NIP must contain 10 digits; got {len(d)} in {nip!r}")
    _reject_all_zeros(d, "NIP")
    weights = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    check = sum(int(a) * w for a, w in zip(d[:9], weights)) % 11
    if check == 10 or check != int(d[9]):
        raise ValueError(f"NIP {d} has an invalid checksum")
    return d


def _regon9_checksum_ok(d9: str) -> bool:
    weights = (8, 9, 2, 3, 4, 5, 6, 7)
    return sum(int(a) * w for a, w in zip(d9[:8], weights)) % 11 % 10 == int(d9[8])


def normalize_regon(regon: str) -> str:
    """Return a clean 9- or 14-digit REGON, validating every checksum.

    A 14-digit REGON embeds a 9-digit parent REGON in its first nine digits, so
    both the parent (9-digit) and the full (14-digit) checksums are verified.
    """
    d = _clean(regon)
    if len(d) not in (9, 14):
        raise ValueError(f"REGON must contain 9 or 14 digits; got {len(d)} in {regon!r}")
    _reject_all_zeros(d, "REGON")
    if not _regon9_checksum_ok(d[:9]):
        raise ValueError(f"REGON {d} has an invalid 9-digit (parent) checksum")
    if len(d) == 14:
        weights = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
        if sum(int(a) * w for a, w in zip(d[:13], weights)) % 11 % 10 != int(d[13]):
            raise ValueError(f"REGON-14 {d} has an invalid 14-digit checksum")
    return d


def normalize_bank_account(bank_account: str) -> str:
    """Return a checksum-validated Polish 26-digit NRB (optional PL prefix)."""
    if not isinstance(bank_account, str):
        raise ValueError("bank_account must be a string")
    value = bank_account.strip()
    if value[:2].upper() == "PL":
        value = value[2:]
    digits = _clean(value)
    if len(digits) != 26:
        raise ValueError("bank_account must contain 26 digits (optionally prefixed PL)")
    _reject_all_zeros(digits, "bank_account")
    # ISO 13616: move the check digits to the end after the numeric PL code.
    if int(digits[2:] + "2521" + digits[:2]) % 97 != 1:
        raise ValueError("bank_account has an invalid checksum")
    return digits


def normalize_date(value: str, *, today: Date | None = None) -> str:
    """Validate YYYY-MM-DD within the register's five preceding calendar years."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        parsed = Date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid YYYY-MM-DD date") from exc
    today = today or datetime.now(ZoneInfo("Europe/Warsaw")).date()
    earliest = max(Date(2019, 9, 1), Date(today.year - 5, 1, 1))
    if not earliest <= parsed <= today:
        raise ValueError(f"date must be between {earliest.isoformat()} and {today.isoformat()}")
    return value


def normalize_identifier(identifier: str, id_type: str, *, check: bool = False) -> tuple[str, str]:
    """Validate an identifier and return its canonical API type and value."""
    normalizers = {"nip": normalize_nip, "regon": normalize_regon}
    if not check:
        normalizers["bank_account"] = normalize_bank_account
    kind = id_type.lower() if isinstance(id_type, str) else ""
    if kind not in normalizers:
        raise ValueError(f"id_type must be one of: {', '.join(normalizers)}")
    return kind, normalizers[kind](identifier)
