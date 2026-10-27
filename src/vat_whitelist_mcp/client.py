"""Small synchronous httpx client for the Ministry of Finance VAT White List API."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Sequence

import httpx

from .errors import VatApiError, VatProtocolError, VatTransportError
from .validate import normalize_bank_account, normalize_date, normalize_identifier

ENDPOINTS = {
    "test": "https://wykazpodatnikowvat-test.mf.gov.pl/api/",
    "prod": "https://wykazpodatnikowvat.mf.gov.pl/api/",
}
MAX_BATCH = 30
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_PATHS = {"nip": "nip", "regon": "regon", "bank_account": "bank-account"}
_BATCH_PATHS = {"nip": "nips", "regon": "regons", "bank_account": "bank-accounts"}


@dataclass
class VatConfig:
    environment: str = "test"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if self.environment not in ENDPOINTS:
            raise ValueError(f"environment must be one of {sorted(ENDPOINTS)}")
        if not (self.timeout > 0 and math.isfinite(self.timeout)):
            raise ValueError("timeout must be a positive finite number")

    @property
    def endpoint(self) -> str:
        return ENDPOINTS[self.environment]


def _subjects(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _api_error(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("code"), str)
        and isinstance(value.get("message"), str)
    )


class VatClient:
    """Reusable REST client; no authentication, retries or background requests."""

    def __init__(self, config: Optional[VatConfig] = None):
        self.config = config or VatConfig()
        self._http = httpx.Client(timeout=self.config.timeout, headers={"Accept": "application/json"})

    def _get(self, path: str, date: str) -> dict:
        try:
            with self._http.stream("GET", self.config.endpoint + path, params={"date": date}) as response:
                status = response.status_code
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise VatProtocolError("response exceeds the maximum allowed size")
                    chunks.append(chunk)
                raw = b"".join(chunks)
        except httpx.HTTPError as exc:
            raise VatTransportError(f"VAT API request failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            if not 200 <= status < 300:
                raise VatTransportError(f"VAT API returned HTTP {status}") from exc
            raise VatProtocolError("VAT API returned invalid JSON") from exc
        if _api_error(payload):
            raise VatApiError(payload["code"], payload["message"], status)
        if not 200 <= status < 300:
            raise VatTransportError(f"VAT API returned HTTP {status}")
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise VatProtocolError("response must contain a result object")
        result = payload["result"]
        for field in ("requestId", "requestDateTime"):
            if not isinstance(result.get(field), str) or not result[field].strip():
                raise VatProtocolError(f"response is missing {field}")
        return result

    def search(self, identifier: str, id_type: str, date: str) -> dict:
        """Return a single lookup result, preserving all upstream subject fields."""
        kind, identifier = normalize_identifier(identifier, id_type)
        date = normalize_date(date)
        result = self._get(f"search/{_PATHS[kind]}/{identifier}", date)
        if kind == "bank_account":
            if not _subjects(result.get("subjects")):
                raise VatProtocolError("account search response must contain a subjects list")
        elif "subject" not in result or (result["subject"] is not None and not isinstance(result["subject"], dict)):
            raise VatProtocolError("search response must contain a subject object or null")
        return result

    def search_bulk(self, identifiers: Sequence[str], id_type: str, date: str) -> dict:
        """Send one batch request and retain per-identifier results and errors."""
        if isinstance(identifiers, (str, bytes)) or not 1 <= len(identifiers) <= MAX_BATCH:
            raise ValueError(f"identifiers must contain between 1 and {MAX_BATCH} items")
        normalized = [normalize_identifier(value, id_type) for value in identifiers]
        kind = normalized[0][0]
        requested = [value for _, value in normalized]
        date = normalize_date(date)
        result = self._get(f"search/{_BATCH_PATHS[kind]}/{','.join(requested)}", date)
        entries = result.get("entries")
        if not isinstance(entries, list):
            raise VatProtocolError("batch response must contain an entries list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("identifier"), str):
                raise VatProtocolError("batch entry must contain an identifier")
            if "error" in entry:
                if not _api_error(entry["error"]) or "subjects" in entry:
                    raise VatProtocolError("batch entry must contain either subjects or a structured error")
            elif not _subjects(entry.get("subjects")):
                raise VatProtocolError("batch entry must contain a subjects list")
        # Never silently label omitted or unexpected identifiers as no matches.
        if Counter(entry["identifier"] for entry in entries) != Counter(requested):
            raise VatProtocolError("batch response identifiers do not match the request")
        return result

    def check_bank_account(self, identifier: str, id_type: str, bank_account: str, date: str) -> dict:
        """Check account association with an active taxpayer; errors remain errors."""
        kind, identifier = normalize_identifier(identifier, id_type, check=True)
        bank_account = normalize_bank_account(bank_account)
        date = normalize_date(date)
        result = self._get(f"check/{kind}/{identifier}/bank-account/{bank_account}", date)
        if result.get("accountAssigned") not in ("TAK", "NIE"):
            raise VatProtocolError("check response must contain accountAssigned TAK or NIE")
        return result

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> VatClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
