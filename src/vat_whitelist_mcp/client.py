"""A small, dependency-light client for the GUS BIR1 REGON SOAP service.

Rather than a full WSDL/SOAP stack, this builds the (very stable) SOAP 1.2
envelopes by hand over ``httpx``. That avoids WCF/WS-Addressing/MTOM pain in
generic SOAP libraries and keeps the runtime tiny.

Session handling:
  * ``Zaloguj(api_key)`` returns a session id (``sid``).
  * The ``sid`` is sent as an HTTP header on every authorized call.
  * Sessions expire after ~60 minutes of inactivity, so the client refreshes
    proactively on a TTL well under that. If the service still rejects a session
    mid-call (a session fault), it re-logs in once and retries — but *only* for a
    positively-identified session fault, never for arbitrary transport errors.
"""

from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence
from xml.sax.saxutils import escape

import httpx

from . import parse as _parse
from .envelopes import NS_ACTION, build_envelope
from .errors import (
    RegonAuthError,
    RegonError,
    RegonProtocolError,
    RegonSessionError,
    RegonTransportError,
)

__all__ = [
    "RegonClient",
    "RegonConfig",
    "RegonError",
    "RegonAuthError",
    "RegonSessionError",
    "RegonTransportError",
    "RegonProtocolError",
    "TEST_KEY",
    "MAX_BATCH",
]

TEST_KEY = "abcde12345abcde12345"

ENDPOINTS = {
    "test": "https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc",
    "prod": "https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc",
}

# Refresh well before the service's ~60-minute inactivity expiry.
_SESSION_TTL = 30 * 60

# GUS accepts at most 20 identifiers in one batch search.
MAX_BATCH = 20

# Reject absurdly large HTTP bodies before we try to parse them.
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024

_ENVELOPE_RE = re.compile(r"<(?:\w+:)?Envelope\b.*</(?:\w+:)?Envelope>", re.S)
# Fault text that indicates the session (sid) was rejected/expired.
_SESSION_FAULT_RE = re.compile(
    r"sesj|session|zaloguj|identyfikator|uwierzytelni|authentic", re.I
)


def _extract_envelope(raw: str) -> str:
    match = _ENVELOPE_RE.search(raw)
    if not match:
        raise RegonProtocolError("no SOAP envelope found in the response")
    return match.group(0)


def _result_text(raw: str, tag: str) -> str:
    """Return the (unescaped) text of ``<tag>`` from a SOAP response body.

    Raises ``RegonSessionError`` for a session-related SOAP fault (recoverable by
    re-login) and ``RegonProtocolError`` for any other fault or missing element.
    """
    envelope = _extract_envelope(raw)
    if re.search(rf"<{tag}\s*/>", envelope):
        return ""
    match = re.search(rf"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>", envelope, re.S)
    if match:
        return html.unescape(match.group(1))
    fault = re.search(r"<(?:\w+:)?Text[^>]*>(.*?)</(?:\w+:)?Text>", envelope, re.S)
    if fault:
        message = fault.group(1).strip()
        if _SESSION_FAULT_RE.search(message):
            raise RegonSessionError(f"session rejected by service: {message}")
        raise RegonProtocolError(f"SOAP fault: {message}")
    raise RegonProtocolError(f"response did not contain <{tag}>")


@dataclass
class RegonConfig:
    api_key: str = TEST_KEY
    environment: str = "test"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if self.environment not in ENDPOINTS:
            raise ValueError(
                f"environment must be one of {sorted(ENDPOINTS)}; got {self.environment!r}"
            )
        if not str(self.api_key).strip():
            raise ValueError("api_key must not be empty")
        if not (self.timeout > 0):
            raise ValueError(f"timeout must be positive; got {self.timeout!r}")

    @property
    def endpoint(self) -> str:
        return ENDPOINTS[self.environment]

    @property
    def is_test_key(self) -> bool:
        return self.api_key == TEST_KEY


class RegonClient:
    """Thread-safe client managing the BIR1 login session lifecycle."""

    def __init__(self, config: Optional[RegonConfig] = None):
        self.config = config or RegonConfig()
        self._sid: Optional[str] = None
        self._sid_at: float = 0.0
        self._lock = threading.RLock()
        self._http = httpx.Client(timeout=self.config.timeout)

    # ---- transport ---------------------------------------------------------
    def _post(self, action: str, body: str, sid: Optional[str]) -> str:
        headers = {
            "Content-Type": (
                f'application/soap+xml;charset=UTF-8;action="{NS_ACTION}/{action}"'
            )
        }
        if sid:
            headers["sid"] = sid
        envelope = build_envelope(self.config.endpoint, action, body)
        try:
            response = self._http.post(
                self.config.endpoint, content=envelope.encode("utf-8"), headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RegonTransportError(
                f"{action} failed: HTTP {exc.response.status_code} from {self.config.endpoint}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RegonTransportError(f"{action} request failed: {exc}") from exc
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise RegonProtocolError(f"{action} response exceeds the maximum allowed size")
        return response.text

    # ---- session -----------------------------------------------------------
    def _wyloguj(self, sid: str) -> bool:
        body = (
            "<ns:Wyloguj><ns:pIdentyfikatorSesji>"
            f"{escape(sid)}"
            "</ns:pIdentyfikatorSesji></ns:Wyloguj>"
        )
        raw = self._post("Wyloguj", body, sid=sid)
        return _result_text(raw, "WylogujResult").strip().lower() == "true"

    def _logout_quiet(self, sid: str) -> None:
        """Best-effort logout so replaced sessions don't leak server-side."""
        try:
            self._wyloguj(sid)
        except RegonError:
            pass

    def _login(self) -> str:
        body = (
            "<ns:Zaloguj><ns:pKluczUzytkownika>"
            f"{escape(self.config.api_key)}"
            "</ns:pKluczUzytkownika></ns:Zaloguj>"
        )
        raw = self._post("Zaloguj", body, sid=None)
        sid = _result_text(raw, "ZalogujResult").strip()
        if not sid:
            raise RegonAuthError("login failed: empty session id (check REGON_API_KEY).")
        return sid

    def _session(self, force: bool = False) -> str:
        with self._lock:
            fresh = self._sid and (time.monotonic() - self._sid_at) < _SESSION_TTL
            if force or not fresh:
                old = self._sid
                self._sid = None
                self._sid_at = 0.0
                if old:
                    self._logout_quiet(old)
                self._sid = self._login()
                self._sid_at = time.monotonic()
            return self._sid

    def _authorized(self, action: str, body: str, result_tag: str) -> str:
        with self._lock:
            raw = self._post(action, body, sid=self._session())
            try:
                return _result_text(raw, result_tag)
            except RegonSessionError:
                # Positively-identified session rejection: re-login once, retry once.
                raw = self._post(action, body, sid=self._session(force=True))
                return _result_text(raw, result_tag)

    def login(self) -> str:
        """Force a fresh login and return the session id."""
        return self._session(force=True)

    def logout(self) -> bool:
        with self._lock:
            if not self._sid:
                return True
            sid = self._sid
            try:
                return self._wyloguj(sid)
            finally:
                self._sid = None
                self._sid_at = 0.0

    # ---- operations --------------------------------------------------------
    def search(
        self,
        *,
        nip: Optional[str] = None,
        regon: Optional[str] = None,
        krs: Optional[str] = None,
        nips: Optional[Sequence[str]] = None,
        krss: Optional[Sequence[str]] = None,
        regons9: Optional[Sequence[str]] = None,
        regons14: Optional[Sequence[str]] = None,
    ) -> list[dict]:
        """Search the register by one identifier or a batch of the same type."""
        for name, seq in (
            ("nips", nips), ("krss", krss), ("regons9", regons9), ("regons14", regons14),
        ):
            if seq is None:
                continue
            if len(seq) == 0:
                raise ValueError(f"{name} must be a non-empty list")
            if len(seq) > MAX_BATCH:
                raise ValueError(f"at most {MAX_BATCH} identifiers per batch search ({name})")
            if any(not str(v).strip() for v in seq):
                raise ValueError(f"{name} contains an empty identifier")
        params = _build_search_params(
            nip=nip, regon=regon, krs=krs,
            nips=nips, krss=krss, regons9=regons9, regons14=regons14,
        )
        body = (
            "<ns:DaneSzukajPodmioty><ns:pParametryWyszukiwania>"
            f"{params}"
            "</ns:pParametryWyszukiwania></ns:DaneSzukajPodmioty>"
        )
        inner = self._authorized(
            "DaneSzukajPodmioty", body, "DaneSzukajPodmiotyResult"
        )
        return _parse.parse_search_results(inner)

    def full_report(self, regon: str, report_name: str) -> list[dict]:
        """Fetch a detailed report for one entity by REGON."""
        body = (
            "<ns:DanePobierzPelnyRaport>"
            f"<ns:pRegon>{escape(regon)}</ns:pRegon>"
            f"<ns:pNazwaRaportu>{escape(report_name)}</ns:pNazwaRaportu>"
            "</ns:DanePobierzPelnyRaport>"
        )
        inner = self._authorized(
            "DanePobierzPelnyRaport", body, "DanePobierzPelnyRaportResult"
        )
        return _parse.parse_report(inner)

    # ---- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        try:
            self.logout()
        except RegonError:
            pass
        self._http.close()

    def __enter__(self) -> "RegonClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_SINGLE_TAGS = {"nip": "Nip", "regon": "Regon", "krs": "Krs"}
_BATCH_TAGS = {
    "nips": "Nipy",
    "krss": "Krsy",
    "regons9": "Regony9zn",
    "regons14": "Regony14zn",
}


def _build_search_params(**kwargs) -> str:
    parts = []
    for key, tag in _SINGLE_TAGS.items():
        value = kwargs.get(key)
        if value:
            parts.append(f"<dat:{tag}>{escape(str(value))}</dat:{tag}>")
    for key, tag in _BATCH_TAGS.items():
        values = kwargs.get(key)
        if values:
            joined = ",".join(escape(str(v)) for v in values)
            parts.append(f"<dat:{tag}>{joined}</dat:{tag}>")
    if not parts:
        raise ValueError(
            "search requires at least one of nip/regon/krs or a batch list"
        )
    if len(parts) > 1:
        raise ValueError("provide only one identifier type per search")
    return parts[0]
