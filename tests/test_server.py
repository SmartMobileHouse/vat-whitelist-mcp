"""MCP discovery, envelopes and configuration without live API calls."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from vat_whitelist_mcp import server
from vat_whitelist_mcp.client import VatClient, VatConfig
from vat_whitelist_mcp.errors import VatApiError

DATE = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_TOOLS = {"search_by_nip", "search_by_regon", "search_by_bank_account", "search_bulk", "check_bank_account"}


@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    monkeypatch.setattr(server, "_config", None)
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.delenv("VAT_ENV", raising=False)
    monkeypatch.delenv("VAT_TIMEOUT", raising=False)


@pytest.fixture
def mock_client(monkeypatch):
    clients = []

    def install(name, status=200):
        payload = json.loads((FIXTURES / f"{name}.json").read_text())
        instance = VatClient()
        instance._http.close()
        instance._http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload)))
        clients.append(instance)
        monkeypatch.setattr(server, "_client", instance)
        return payload

    yield install
    for instance in clients:
        instance.close()


def test_tools_registered_with_required_dates():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert "date" in tool.input_schema["required"]


def test_search_envelope_retains_details_and_confirmation(mock_client):
    payload = mock_client("search_result")
    result = server.search_by_nip("3245174504", DATE)
    assert result["results"] == [payload["result"]["subject"]]
    assert result["count"] == 1
    assert result["requestId"] == "test-confirmation"
    assert result["requestDateTime"] == payload["result"]["requestDateTime"]
    assert result["date"] == DATE
    assert result["source"]["environment"] == "test"
    assert "VAT White List" in result["source"]["register"]
    assert datetime.fromisoformat(result["source"]["retrieved_at"]).utcoffset().total_seconds() == 0


def test_bulk_does_not_treat_entry_errors_as_unmatched(mock_client):
    payload = mock_client("batch_result")
    result = server.search_bulk(["324-517-45-04", "1854510877", "7250018312"], "nip", DATE)
    assert result["results"] == payload["result"]["entries"]
    assert result["count"] == 3
    assert result["requested"] == ["3245174504", "1854510877", "7250018312"]
    assert result["unmatched"] == ["1854510877"]
    assert result["requestId"] == "batch-confirmation"


def test_check_envelope_retains_upstream_answer(mock_client):
    mock_client("check_result")
    result = server.check_bank_account("3245174504", "nip", "70506405335016096312945164", DATE)
    assert result["accountAssigned"] == "TAK"
    assert result["requestId"] == "check-confirmation"
    assert result["date"] == DATE
    assert "source" in result


def test_errors_propagate_from_tools(mock_client):
    mock_client("error", 429)
    with pytest.raises(VatApiError, match="WL-191"):
        server.check_bank_account("3245174504", "nip", "70506405335016096312945164", DATE)


@pytest.mark.parametrize("name,value", [("VAT_ENV", "unknown"), ("VAT_TIMEOUT", "no"), ("VAT_TIMEOUT", "0"), ("VAT_TIMEOUT", "nan"), ("VAT_TIMEOUT", "inf")])
def test_invalid_environment_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        server._load_config()


def test_production_config(monkeypatch):
    monkeypatch.setenv("VAT_ENV", "prod")
    monkeypatch.setenv("VAT_TIMEOUT", "12.5")
    assert server._load_config() == VatConfig(environment="prod", timeout=12.5)


def test_main_closes_client_on_exit(monkeypatch):
    class Client:
        closed = False
        def close(self):
            self.closed = True

    instance = Client()
    monkeypatch.setattr(server, "_client", instance)

    def run():
        raise RuntimeError("closed")

    monkeypatch.setattr(server.mcp, "run", run)
    with pytest.raises(RuntimeError, match="closed"):
        server.main()
    assert instance.closed


def test_stdio_tool_discovery_and_input_error():
    """Exercise the installed module through the real MCP stdio transport."""
    import sys
    from mcp.client import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def exercise():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "vat_whitelist_mcp"], env={"VAT_ENV": "test"})
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                result = await session.list_tools()
                assert {tool.name for tool in result.tools} == EXPECTED_TOOLS
                invalid = await session.call_tool("search_by_nip", {"nip": "invalid", "date": DATE})
                assert invalid.is_error

    asyncio.run(exercise())
