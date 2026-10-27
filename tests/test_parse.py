from pathlib import Path

from vat_whitelist_mcp import parse

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_search_results_maps_fields():
    rows = parse.parse_search_results(_load("search_result.xml"))
    assert len(rows) == 1
    row = rows[0]
    assert row["regon"] == "000331501"
    assert row["nip"] == "5261040567"
    assert row["name"] == "PRZYKLADOWA SPOLKA AKCYJNA"
    assert row["postal_code"] == "00925"
    assert row["type"] == "P"
    assert row["type_label"] == "legal person"
    # Empty elements become None, not "".
    assert row["unit_number"] is None
    assert row["nip_status"] is None


def test_parse_search_results_empty():
    assert parse.parse_search_results("") == []


def test_parse_report_snake_cases_tags():
    rows = parse.parse_report(_load("full_report.xml"))
    assert len(rows) == 1
    row = rows[0]
    assert row["praw_regon9"] == "000331501"
    assert row["praw_nazwa"] == "PRZYKLADOWA SPOLKA AKCYJNA"
    assert row["praw_ad_siedz_kod_pocztowy"] == "00925"
