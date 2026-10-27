"""Mocked-transport tests for the session lifecycle and response handling.

These use httpx.MockTransport so no network is touched: they verify login/sid
parsing, session reuse within the TTL, MTOM extraction, that a session fault
triggers exactly one re-login + retry, that transport errors propagate WITHOUT a
re-login storm, and that malformed inner XML surfaces as a protocol error.
"""

import re

import httpx
import pytest

from vat_whitelist_mcp.client import (
    RegonClient,
    RegonConfig,
    RegonProtocolError,
    RegonTransportError,
)

NS = "http://CIS/BIR/PUBL/2014/07"

GUS_ROW = (
    "&lt;root&gt;&lt;dane&gt;&lt;Nip&gt;5261040828&lt;/Nip&gt;"
    "&lt;Nazwa&gt;GUS&lt;/Nazwa&gt;&lt;Typ&gt;P&lt;/Typ&gt;&lt;/dane&gt;&lt;/root&gt;"
)


def _mtom(body_inner: str) -> str:
    env = (
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"<s:Body>{body_inner}</s:Body></s:Envelope>"
    )
    return (
        "\r\n--uuid:boundary\r\n"
        'Content-Type: application/xop+xml;charset=utf-8;type="application/soap+xml"\r\n\r\n'
        f"{env}\r\n--uuid:boundary--\r\n"
    )


def _zaloguj(sid):
    return _mtom(f'<ZalogujResponse xmlns="{NS}"><ZalogujResult>{sid}</ZalogujResult></ZalogujResponse>')


def _wyloguj():
    return _mtom(f'<WylogujResponse xmlns="{NS}"><WylogujResult>true</WylogujResult></WylogujResponse>')


def _search(inner):
    return _mtom(
        f'<DaneSzukajPodmiotyResponse xmlns="{NS}">'
        f"<DaneSzukajPodmiotyResult>{inner}</DaneSzukajPodmiotyResult></DaneSzukajPodmiotyResponse>"
    )


def _fault(text):
    return _mtom(
        "<s:Fault><s:Code><s:Value>s:Receiver</s:Value></s:Code>"
        f'<s:Reason><s:Text xml:lang="pl">{text}</s:Text></s:Reason></s:Fault>'
    )


def _action(request):
    m = re.search(r'action="([^"]+)"', request.headers.get("content-type", ""))
    return m.group(1).rsplit("/", 1)[-1] if m else ""


class FakeGus:
    def __init__(self, mode="ok"):
        self.mode = mode  # "ok" | "expire_once" | "malformed"
        self.zaloguj = self.search = self.wyloguj = 0

    def handler(self, request):
        action = _action(request)
        if action == "Zaloguj":
            self.zaloguj += 1
            return httpx.Response(200, text=_zaloguj(f"SID{self.zaloguj}"))
        if action == "Wyloguj":
            self.wyloguj += 1
            return httpx.Response(200, text=_wyloguj())
        if action == "DaneSzukajPodmioty":
            self.search += 1
            if self.mode == "expire_once" and self.search == 1:
                return httpx.Response(200, text=_fault("Identyfikator sesji jest niepoprawny"))
            if self.mode == "malformed":
                return httpx.Response(200, text=_search("&lt;root&gt;&lt;dane&gt;&lt;Nip&gt;"))
            return httpx.Response(200, text=_search(GUS_ROW))
        return httpx.Response(500)


def _client(handler):
    c = RegonClient(RegonConfig(api_key="k", environment="prod"))
    c._http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def test_login_parses_sid():
    fake = FakeGus()
    assert _client(fake.handler).login() == "SID1"
    assert fake.zaloguj == 1


def test_session_reused_within_ttl():
    fake = FakeGus()
    c = _client(fake.handler)
    c.search(nip="5261040828")
    c.search(nip="5261040828")
    assert fake.zaloguj == 1  # one login serves both searches
    assert fake.search == 2


def test_mtom_extraction_and_parsing():
    rows = _client(FakeGus().handler).search(nip="5261040828")
    assert rows and rows[0]["name"] == "GUS" and rows[0]["type_label"] == "legal person"


def test_session_fault_triggers_single_retry():
    fake = FakeGus(mode="expire_once")
    rows = _client(fake.handler).search(nip="5261040828")
    assert rows and rows[0]["name"] == "GUS"
    assert fake.zaloguj == 2  # initial login + exactly one re-login
    assert fake.search == 2  # faulted call + one retry


def test_transport_error_on_login_propagates():
    def boom(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(RegonTransportError):
        _client(boom).login()


def test_transport_error_on_search_does_not_relogin():
    state = {"zaloguj": 0}

    def handler(request):
        if _action(request) == "Zaloguj":
            state["zaloguj"] += 1
            return httpx.Response(200, text=_zaloguj("SID1"))
        raise httpx.ReadTimeout("slow", request=request)

    c = _client(handler)
    with pytest.raises(RegonTransportError):
        c.search(nip="5261040828")
    assert state["zaloguj"] == 1  # no re-login storm on a transport error


def test_malformed_inner_xml_raises_protocol_error():
    with pytest.raises(RegonProtocolError):
        _client(FakeGus(mode="malformed").handler).search(nip="5261040828")


def test_logout_calls_wyloguj():
    fake = FakeGus()
    c = _client(fake.handler)
    c.login()
    assert c.logout() is True
    assert fake.wyloguj == 1
