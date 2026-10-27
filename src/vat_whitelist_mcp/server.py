"""MCP tools for the Polish VAT White List, served over stdio."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from mcp.server import MCPServer

from .client import VatClient, VatConfig
from .validate import normalize_identifier

mcp = MCPServer("vat-whitelist")
_config: Optional[VatConfig] = None
_client: Optional[VatClient] = None


def _load_config() -> VatConfig:
    global _config
    if _config is None:
        raw_timeout = os.getenv("VAT_TIMEOUT", "30")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError(f"VAT_TIMEOUT must be a number; got {raw_timeout!r}") from exc
        _config = VatConfig(environment=os.getenv("VAT_ENV", "test"), timeout=timeout)
    return _config


def _get_client() -> VatClient:
    global _client
    if _client is None:
        _client = VatClient(_load_config())
    return _client


def _source() -> dict:
    return {
        "register": "VAT White List — Wykaz podatników VAT",
        "provided_by": "Ministerstwo Finansów / Krajowa Administracja Skarbowa",
        "api": "VAT White List",
        "environment": _load_config().environment,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _envelope(result: dict, date: str, field: str) -> dict:
    metadata = {key: value for key, value in result.items() if key != field}
    value = result[field]
    rows = ([] if value is None else [value]) if field == "subject" else value
    return {**metadata, "count": len(rows), "results": rows, "date": date, "source": _source()}


@mcp.tool()
def search_by_nip(nip: str, date: str) -> dict:
    """Look up taxpayer details by NIP on an explicit YYYY-MM-DD date."""
    return _envelope(_get_client().search(nip, "nip", date), date, "subject")


@mcp.tool()
def search_by_regon(regon: str, date: str) -> dict:
    """Look up taxpayer details by 9- or 14-digit REGON on YYYY-MM-DD."""
    return _envelope(_get_client().search(regon, "regon", date), date, "subject")


@mcp.tool()
def search_by_bank_account(bank_account: str, date: str) -> dict:
    """Find taxpayers for a Polish bank account on YYYY-MM-DD; accepts NRB or PL IBAN."""
    return _envelope(_get_client().search(bank_account, "bank_account", date), date, "subjects")


@mcp.tool()
def search_bulk(identifiers: list[str], id_type: str, date: str) -> dict:
    """Look up 1–30 identifiers in one request on YYYY-MM-DD.

    id_type: nip, regon, or bank_account. Results retain each identifier's
    subjects or API error. Only successful empty entries appear in unmatched.
    count is the number of returned entries, not the number of taxpayers.
    """
    result = _get_client().search_bulk(identifiers, id_type, date)
    envelope = _envelope(result, date, "entries")
    envelope["requested"] = [normalize_identifier(value, id_type)[1] for value in identifiers]
    envelope["unmatched"] = [entry["identifier"] for entry in result["entries"] if entry.get("subjects") == []]
    return envelope


@mcp.tool()
def check_bank_account(identifier: str, id_type: str, bank_account: str, date: str) -> dict:
    """Check account association with an active taxpayer on YYYY-MM-DD.

    id_type: nip or regon. accountAssigned is the API's TAK/NIE answer; API
    failures raise errors and must never be interpreted as a negative match.
    """
    result = _get_client().check_bank_account(identifier, id_type, bank_account, date)
    return {**result, "date": date, "source": _source()}


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    try:
        mcp.run()
    finally:
        if _client is not None:
            _client.close()
