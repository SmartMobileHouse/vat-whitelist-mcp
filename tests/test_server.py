"""Offline MCP-surface tests: tool discovery + no-network tool behavior."""

import asyncio

import pytest

from vat_whitelist_mcp import server

EXPECTED_TOOLS = [
    "get_full_report",
    "list_report_types",
    "search_bulk",
    "search_by_krs",
    "search_by_nip",
    "search_by_regon",
]


def test_all_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(t.name for t in tools) == EXPECTED_TOOLS


def test_list_report_types_offline_has_source():
    out = server.list_report_types()
    assert out["count"] == len(server.REPORT_TYPES)
    assert out["source"]["api"] == "BIR1.1"
    assert "attribution" in out["source"]


def test_invalid_identifier_rejected_before_network():
    # normalize_* raises ValueError before any BIR call is made.
    with pytest.raises(ValueError):
        server.search_by_nip("abc")
    with pytest.raises(ValueError):
        server.get_full_report("000331501", "NotAReport")
