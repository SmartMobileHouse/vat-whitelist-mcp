"""Opt-in sandbox contract test; never queries production during default tests."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from vat_whitelist_mcp.client import VatClient, VatConfig

pytestmark = pytest.mark.network


@pytest.mark.skipif(os.getenv("VAT_RUN_NETWORK") != "1", reason="set VAT_RUN_NETWORK=1 for sandbox tests")
def test_official_sandbox_taxpayer():
    # NIP from the Ministry's published API test dataset.
    date = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
    with VatClient(VatConfig(environment="test")) as client:
        result = client.search("3245174504", "nip", date)
        assert result["subject"]["nip"] == "3245174504"
        assert result["requestId"]
        assert result["requestDateTime"]


@pytest.mark.skipif(os.getenv("VAT_RUN_NETWORK") != "1", reason="set VAT_RUN_NETWORK=1 for sandbox tests")
def test_sandbox_search_and_check_contracts():
    date = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
    with VatClient() as client:
        regon = client.search("755016841", "regon", date)
        assert regon["subject"] is None or regon["subject"]["regon"] == "755016841"
        accounts = client.search("70506405335016096312945164", "bank_account", date)
        assert isinstance(accounts["subjects"], list)
        bulk = client.search_bulk(["3245174504", "1854510877"], "nip", date)
        assert {entry["identifier"] for entry in bulk["entries"]} == {"3245174504", "1854510877"}
        checked = client.check_bank_account("3245174504", "nip", "70506405335016096312945164", date)
        assert checked["accountAssigned"] in ("TAK", "NIE")
