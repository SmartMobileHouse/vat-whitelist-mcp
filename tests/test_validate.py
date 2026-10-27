import pytest

from vat_whitelist_mcp.validate import normalize_nip, normalize_regon

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



from datetime import date

from vat_whitelist_mcp.validate import normalize_bank_account, normalize_date


@pytest.mark.parametrize("value", ["70506405335016096312945164", "PL70 5064 0533 5016 0963 1294 5164", "pl70506405335016096312945164"])
def test_bank_account_normalizes_to_nrb(value):
    assert normalize_bank_account(value) == "70506405335016096312945164"


@pytest.mark.parametrize("value", ["70506405335016096312945165", "0" * 26, "DE70506405335016096312945164", "123", "abc", None, 70506405335016096312945164])
def test_bank_account_rejects_invalid_input(value):
    with pytest.raises(ValueError):
        normalize_bank_account(value)


@pytest.mark.parametrize("value", ["５２６１０４０８２８", "٥٢٦١٠٤٠٨٢٨", None, 5261040828])
def test_nip_rejects_non_ascii_or_non_string(value):
    with pytest.raises(ValueError):
        normalize_nip(value)


@pytest.mark.parametrize("value", ["2021-01-01", "2024-02-29", "2026-10-27"])
def test_date_accepts_calendar_year_window(value):
    assert normalize_date(value, today=date(2026, 10, 27)) == value


@pytest.mark.parametrize("value", ["2020-12-31", "2026-10-28", "2024-02-30", "2026-1-01", "20260101", " 2026-01-01", None])
def test_date_rejects_invalid_out_of_range_and_future(value):
    with pytest.raises(ValueError):
        normalize_date(value, today=date(2026, 10, 27))


def test_date_window_advances_at_year_boundary():
    assert normalize_date("2021-01-01", today=date(2026, 12, 31)) == "2021-01-01"
    with pytest.raises(ValueError):
        normalize_date("2021-12-31", today=date(2027, 1, 1))
