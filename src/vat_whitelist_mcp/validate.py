"""Validation and normalization for Polish business identifiers.

Checksums are verified locally so obviously-wrong identifiers fail fast without
a network round-trip. Only whitespace and common grouping separators (``-`` and
``.``) are tolerated in the input; any other character is rejected rather than
silently stripped, so ``"abc5261040828"`` is an error, not a valid NIP.
"""

from __future__ import annotations

import re

# Characters allowed purely as visual separators in a typed identifier.
_SEPARATORS = re.compile(r"[\s.\-]")
_ALL_DIGITS = re.compile(r"\A\d+\Z")


def _clean(value: str) -> str:
    """Strip only whitespace/grouping separators; reject anything non-numeric."""
    if value is None:
        raise ValueError("identifier must not be None")
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


def normalize_krs(krs: str) -> str:
    """Return a zero-padded 10-digit KRS (no checksum exists).

    Leading zeros are routinely omitted when a KRS is typed (``543759`` for
    ``0000543759``), so a shorter numeric value is left-padded to 10 digits.
    All-zero and over-long values are rejected.
    """
    d = _clean(krs)
    if not d or len(d) > 10:
        raise ValueError(f"KRS must contain 1 to 10 digits; got {krs!r}")
    padded = d.zfill(10)
    _reject_all_zeros(padded, "KRS")
    return padded
