import pytest

from vat_whitelist_mcp.validate import normalize_krs, normalize_nip, normalize_regon

# --- NIP -------------------------------------------------------------------

def test_nip_valid_strips_separators():
    assert normalize_nip("526-104-08-28") == "5261040828"
    assert normalize_nip("  526.104.08.28 ") == "5261040828"


def test_nip_rejects_alpha_contamination():
    # Non-separator characters must be rejected, not silently removed.
    with pytest.raises(ValueError):
        normalize_nip("abc5261040828")
    with pytest.raises(ValueError):
        normalize_nip("5261040828x")


def test_nip_rejects_bad_checksum():
    with pytest.raises(ValueError):
        normalize_nip("5261040829")


def test_nip_rejects_wrong_length():
    with pytest.raises(ValueError):
        normalize_nip("12345")


def test_nip_rejects_all_zeros():
    with pytest.raises(ValueError):
        normalize_nip("0000000000")


# --- REGON -----------------------------------------------------------------

def test_regon9_valid_preserves_leading_zeros():
    assert normalize_regon("000331501") == "000331501"


def test_regon14_valid():
    # 000331501 (valid parent) + local unit + valid 14-digit check digit.
    assert normalize_regon("00033150100017") == "00033150100017"


def test_regon_rejects_bad_checksum():
    with pytest.raises(ValueError):
        normalize_regon("000331502")


def test_regon14_rejects_invalid_embedded_regon9():
    # Parent portion 000331502 is not a valid REGON-9.
    with pytest.raises(ValueError):
        normalize_regon("00033150200007")


def test_regon_rejects_all_zeros():
    with pytest.raises(ValueError):
        normalize_regon("000000000")


def test_regon_rejects_wrong_length():
    with pytest.raises(ValueError):
        normalize_regon("12345")


# --- KRS -------------------------------------------------------------------

def test_krs_zero_pads_short_input():
    assert normalize_krs("543759") == "0000543759"
    assert normalize_krs("0000543759") == "0000543759"


def test_krs_rejects_all_zeros():
    with pytest.raises(ValueError):
        normalize_krs("0000000000")
    with pytest.raises(ValueError):
        normalize_krs("0")


def test_krs_rejects_too_long_or_alpha():
    with pytest.raises(ValueError):
        normalize_krs("12345678901")
    with pytest.raises(ValueError):
        normalize_krs("12ab")
