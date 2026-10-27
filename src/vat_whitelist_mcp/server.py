"""MCP server exposing the GUS REGON register as clean, typed tools."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Optional

from mcp.server import MCPServer

from .client import MAX_BATCH, RegonClient, RegonConfig, TEST_KEY
from .validate import normalize_krs, normalize_nip, normalize_regon

mcp = MCPServer("regon")

_config: Optional[RegonConfig] = None
_client: Optional[RegonClient] = None

# Report names accepted by get_full_report(). These are the BIR1.1 reports; the
# newer BIR1.2 / PKD-2025 report family belongs to a different API version and
# is intentionally out of scope for this client.
REPORT_TYPES = {
    "BIR11OsPrawna": "Legal person — full record (type P).",
    "BIR11OsPrawnaPkd": "Legal person — PKD activity codes.",
    "BIR11OsPrawnaListaJednLokalnych": "Legal person — list of local units.",
    "BIR11JednLokalnaOsPrawnej": "Local unit of a legal person — full record.",
    "BIR11JednLokalnaOsPrawnejPkd": "Local unit of a legal person — PKD codes.",
    "BIR11OsFizycznaDaneOgolne": "Natural person — general data (type F).",
    "BIR11OsFizycznaDzialalnoscCeidg": "Natural person — CEIDG business activity (silo 1).",
    "BIR11OsFizycznaDzialalnoscRolnicza": "Natural person — agricultural activity (silo 2).",
    "BIR11OsFizycznaDzialalnoscPozostala": "Natural person — other activity (silo 3).",
    "BIR11OsFizycznaDzialalnoscSkreslonaDo20141108": "Natural person — activity removed before 2014-11-08 (silo 4).",
    "BIR11OsFizycznaPkd": "Natural person — PKD activity codes.",
    "BIR11OsFizycznaListaJednLokalnych": "Natural person — list of local units.",
    "BIR11JednLokalnaOsFizycznej": "Local unit of a natural person — full record.",
    "BIR11JednLokalnaOsFizycznejPkd": "Local unit of a natural person — PKD codes.",
}


def _load_config() -> RegonConfig:
    """Read and eagerly validate configuration from the environment."""
    global _config
    if _config is None:
        raw_timeout = os.getenv("REGON_TIMEOUT", "30")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError(f"REGON_TIMEOUT must be a number; got {raw_timeout!r}") from exc
        if not (timeout > 0 and math.isfinite(timeout)):
            raise ValueError(f"REGON_TIMEOUT must be a positive finite number; got {timeout!r}")
        # RegonConfig validates api_key non-empty and environment membership.
        _config = RegonConfig(
            api_key=os.getenv("REGON_API_KEY", TEST_KEY),
            environment=os.getenv("REGON_ENV", "test"),
            timeout=timeout,
        )
    return _config


def _get_client() -> RegonClient:
    global _client
    if _client is None:
        _client = RegonClient(_load_config())
    return _client


def _source() -> dict:
    config = _load_config()
    source = {
        "register": "REGON — Krajowy Rejestr Urzędowy Podmiotów Gospodarki Narodowej",
        "provided_by": "Główny Urząd Statystyczny (Statistics Poland / GUS)",
        "api": "BIR1.1",
        "environment": config.environment,
        "using_test_key": config.is_test_key,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attribution": (
            "When presenting REGON data, cite the source as 'REGON, GUS' "
            "together with the retrieval date."
        ),
    }
    if config.is_test_key:
        source["note"] = (
            "Public test key in use — the GUS test database is anonymized and "
            "returns limited or no data. Set REGON_API_KEY to a production "
            "USER_KEY (and REGON_ENV=prod) for live results."
        )
    return source


def _envelope(results: list[dict]) -> dict:
    return {"count": len(results), "results": results, "source": _source()}


@mcp.tool()
def search_by_nip(nip: str) -> dict:
    """Look up a Polish business entity by NIP (10-digit tax id).

    Returns basic registry data (name, REGON, address, entity type). Use the
    returned REGON with get_full_report() for the detailed record.
    """
    return _envelope(_get_client().search(nip=normalize_nip(nip)))


@mcp.tool()
def search_by_regon(regon: str) -> dict:
    """Look up a Polish business entity by REGON (9- or 14-digit statistical id)."""
    return _envelope(_get_client().search(regon=normalize_regon(regon)))


@mcp.tool()
def search_by_krs(krs: str) -> dict:
    """Look up a Polish business entity by KRS (10-digit court-register number)."""
    return _envelope(_get_client().search(krs=normalize_krs(krs)))


@mcp.tool()
def search_bulk(identifiers: list[str], id_type: str) -> dict:
    """Look up up to 20 entities of the same identifier type in one call.

    id_type must be one of: "nip", "krs", "regon9", "regon14".

    The response adds `requested` (normalized inputs) and `unmatched` (requested
    ids with no returned row) so partial results are explicit. For KRS the
    service does not echo the KRS in search rows, so `unmatched` is null there.
    """
    if not identifiers:
        raise ValueError("identifiers must be a non-empty list")
    if len(identifiers) > MAX_BATCH:
        raise ValueError(f"GUS BIR accepts at most {MAX_BATCH} identifiers per bulk search")

    kind = id_type.lower()
    client = _get_client()
    if kind == "nip":
        requested = [normalize_nip(x) for x in identifiers]
        rows = client.search(nips=requested)
        match_field = "nip"
    elif kind == "krs":
        requested = [normalize_krs(x) for x in identifiers]
        rows = client.search(krss=requested)
        match_field = None  # search rows do not include KRS
    elif kind == "regon9":
        requested = [normalize_regon(x) for x in identifiers]
        if any(len(v) != 9 for v in requested):
            raise ValueError("regon9 expects 9-digit REGONs")
        rows = client.search(regons9=requested)
        match_field = "regon"
    elif kind == "regon14":
        requested = [normalize_regon(x) for x in identifiers]
        if any(len(v) != 14 for v in requested):
            raise ValueError("regon14 expects 14-digit REGONs")
        rows = client.search(regons14=requested)
        match_field = "regon"
    else:
        raise ValueError("id_type must be one of: nip, krs, regon9, regon14")

    envelope = _envelope(rows)
    envelope["requested"] = requested
    if match_field:
        found = {r.get(match_field) for r in rows}
        envelope["unmatched"] = [x for x in requested if x not in found]
    else:
        envelope["unmatched"] = None
    return envelope


@mcp.tool()
def get_full_report(regon: str, report_type: str) -> dict:
    """Fetch a detailed REGON report for one entity by REGON.

    Choose report_type from list_report_types(), based on the entity's `type`
    and `silo_id` returned by a search.
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(
            f"Unknown report_type {report_type!r}. Call list_report_types() for valid names."
        )
    return _envelope(_get_client().full_report(normalize_regon(regon), report_type))


@mcp.tool()
def list_report_types() -> dict:
    """List valid report_type values for get_full_report(), with guidance.

    These are the BIR1.1 report names. Picking the right report:
      - type "P" (legal person)   -> BIR11OsPrawna
      - type "F" (natural person) -> by silo_id:
          1 -> BIR11OsFizycznaDzialalnoscCeidg
          2 -> BIR11OsFizycznaDzialalnoscRolnicza
          3 -> BIR11OsFizycznaDzialalnoscPozostala
          4 -> BIR11OsFizycznaDzialalnoscSkreslonaDo20141108
      - local units (LP / LF) -> BIR11JednLokalnaOsPrawnej / ...OsFizycznej
    """
    return {
        "report_types": REPORT_TYPES,
        "count": len(REPORT_TYPES),
        "source": _source(),
    }


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    try:
        mcp.run()
    finally:
        if _client is not None:
            _client.close()
