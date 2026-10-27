"""Parse the XML payloads returned inside BIR1 responses into plain dicts.

Search and report results arrive as an XML *string* embedded (HTML-escaped)
inside the SOAP result element. Once unescaped, that inner document looks like::

    <root>
      <dane> ... fields ... </dane>
      <dane> ... </dane>
    </root>

Each ``<dane>`` is one matched entity.

The inner XML comes from an external service, so it is parsed with
``defusedxml`` (DTDs and entity declarations rejected) under a size cap to keep
the long-running MCP process safe from entity-expansion / resource-exhaustion.
"""

from __future__ import annotations

import re
from typing import Optional
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring as _safe_fromstring

from .errors import RegonProtocolError

# Generous ceiling for a single REGON payload (real ones are a few KB).
_MAX_INNER_BYTES = 8 * 1024 * 1024

# Friendly snake_case names for the fields returned by DaneSzukajPodmioty.
_SEARCH_FIELDS = {
    "Regon": "regon",
    "Nip": "nip",
    "StatusNip": "nip_status",
    "Nazwa": "name",
    "Wojewodztwo": "voivodeship",
    "Powiat": "county",
    "Gmina": "commune",
    "Miejscowosc": "city",
    "KodPocztowy": "postal_code",
    "Ulica": "street",
    "NrNieruchomosci": "building_number",
    "NrLokalu": "unit_number",
    "Typ": "type",
    "SilosID": "silo_id",
    "DataZakonczeniaDzialalnosci": "activity_end_date",
    "MiejscowoscPoczty": "post_office_city",
}

# BIR entity type codes.
TYPE_LABELS = {
    "P": "legal person",
    "F": "natural person",
    "LP": "local unit of a legal person",
    "LF": "local unit of a natural person",
}

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _text(element: Element) -> Optional[str]:
    value = (element.text or "").strip()
    return value or None


def _rows(inner_xml: str) -> list[Element]:
    """Return the ``<dane>`` elements from a result payload.

    An empty payload is a legitimate zero-result response; a non-empty but
    unparseable payload is a protocol error, not "no results".
    """
    inner = (inner_xml or "").strip()
    if not inner:
        return []
    if len(inner.encode("utf-8", "ignore")) > _MAX_INNER_BYTES:
        raise RegonProtocolError("REGON payload exceeds the maximum allowed size")
    try:
        root = _safe_fromstring(inner)
    except (ParseError, ValueError) as exc:
        raise RegonProtocolError(f"could not parse REGON XML payload: {exc}") from exc
    return list(root.findall("dane"))


def parse_search_results(inner_xml: str) -> list[dict]:
    """Parse a DaneSzukajPodmioty payload into a list of entity summaries."""
    results = []
    for dane in _rows(inner_xml):
        row = {
            _SEARCH_FIELDS.get(child.tag, _snake(child.tag)): _text(child)
            for child in dane
        }
        if row.get("type"):
            row["type_label"] = TYPE_LABELS.get(row["type"], row["type"])
        results.append(row)
    return results


def parse_report(inner_xml: str) -> list[dict]:
    """Parse a DanePobierzPelnyRaport payload generically (tag -> snake_case)."""
    return [
        {_snake(child.tag): _text(child) for child in dane}
        for dane in _rows(inner_xml)
    ]
