"""Offline contract tests using mocked HTTP, including partial batch failures."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from vat_whitelist_mcp import client as module
from vat_whitelist_mcp.client import ENDPOINTS, VatClient, VatConfig
from vat_whitelist_mcp.errors import VatApiError, VatProtocolError, VatTransportError

DATE = datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
NIP = "3245174504"
REGON = "755016841"
ACCOUNT = "70506405335016096312945164"
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def make_client():
    clients = []

    def make(handler, config=None):
        instance = VatClient(config)
        instance._http.close()
        instance._http = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(instance)
        return instance

    yield make
    for instance in clients:
        instance.close()


@pytest.mark.parametrize("kind,value,path", [("nip", NIP, "nip"), ("regon", REGON, "regon"), ("bank_account", ACCOUNT, "bank-account")])
@pytest.mark.parametrize("environment", ["test", "prod"])
def test_search_routes_and_preserves_full_response(make_client, kind, value, path, environment):
    payload = fixture("search_result")
    if kind == "bank_account":
        payload["result"]["subjects"] = [payload["result"].pop("subject")]

    def handler(request):
        assert request.method == "GET"
        assert str(request.url).split("?")[0] == ENDPOINTS[environment] + f"search/{path}/{value}"
        assert dict(request.url.params) == {"date": DATE}
        return httpx.Response(200, json=payload)

    with make_client(handler, VatConfig(environment=environment)) as instance:
        assert instance.search(value, kind, DATE) == payload["result"]


@pytest.mark.parametrize("kind,values,path", [
    ("nip", [NIP, "1854510877"], "nips"),
    ("regon", [REGON, "000331501"], "regons"),
    ("bank_account", [ACCOUNT, "61109010140000071219812874"], "bank-accounts"),
])
def test_batch_uses_one_plural_endpoint(make_client, kind, values, path):
    calls = []
    payload = fixture("batch_result")
    payload["result"]["entries"] = [{"identifier": v, "subjects": []} for v in reversed(values)]

    def handler(request):
        calls.append(request)
        assert request.url.path == f"/api/search/{path}/{','.join(values)}"
        assert dict(request.url.params) == {"date": DATE}
        return httpx.Response(200, json=payload)

    assert make_client(handler).search_bulk(values, kind, DATE) == payload["result"]
    assert len(calls) == 1


def test_batch_preserves_success_empty_and_error_entries(make_client):
    payload = fixture("batch_result")
    instance = make_client(lambda _: httpx.Response(200, json=payload))
    assert instance.search_bulk([NIP, "1854510877", "7250018312"], "nip", DATE) == payload["result"]


@pytest.mark.parametrize("kind,value", [("nip", NIP), ("regon", REGON)])
@pytest.mark.parametrize("answer", ["TAK", "NIE"])
def test_check_both_identifiers_and_answers(make_client, kind, value, answer):
    payload = fixture("check_result")
    payload["result"]["accountAssigned"] = answer

    def handler(request):
        assert request.url.path == f"/api/check/{kind}/{value}/bank-account/{ACCOUNT}"
        assert dict(request.url.params) == {"date": DATE}
        return httpx.Response(200, json=payload)

    result = make_client(handler).check_bank_account(value, kind, "PL" + ACCOUNT, DATE)
    assert result == payload["result"]


@pytest.mark.parametrize("operation", [
    lambda c: c.search("bad", "nip", DATE),
    lambda c: c.search(NIP, "krs", DATE),
    lambda c: c.search(NIP, "nip", "2999-01-01"),
    lambda c: c.search(NIP, "nip", "2024-02-30"),
    lambda c: c.search_bulk([], "nip", DATE),
    lambda c: c.search_bulk([NIP] * 31, "nip", DATE),
    lambda c: c.search_bulk([NIP, "bad"], "nip", DATE),
    lambda c: c.search_bulk(NIP, "nip", DATE),
    lambda c: c.check_bank_account(NIP, "bank_account", ACCOUNT, DATE),
    lambda c: c.check_bank_account(NIP, "nip", "invalid", DATE),
])
def test_invalid_input_never_sends_http(make_client, operation):
    def handler(_):
        pytest.fail("invalid input must not send a request")

    with pytest.raises(ValueError):
        operation(make_client(handler))


@pytest.mark.parametrize("payload,kind", [
    ({"subject": None}, "nip"),
    ({"subjects": []}, "bank_account"),
])
def test_explicit_no_matches(make_client, payload, kind):
    payload.update(requestId="confirmation", requestDateTime="27-10-2026 12:00:00")
    result = make_client(lambda _: httpx.Response(200, json={"result": payload})).search(ACCOUNT if kind == "bank_account" else NIP, kind, DATE)
    assert result == payload


@pytest.mark.parametrize("status,code", [(400, "WL-118"), (429, "WL-191"), (500, "WL-197"), (200, "WL-195")])
def test_api_errors_are_not_negative_checks_or_empty_searches(make_client, status, code):
    calls = []
    payload = {"code": code, "message": "Upstream error"}

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=payload)

    instance = make_client(handler)
    with pytest.raises(VatApiError) as caught:
        instance.check_bank_account(NIP, "nip", ACCOUNT, DATE)
    assert (caught.value.code, caught.value.message, caught.value.status_code) == (code, payload["message"], status)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [302, 404, 503])
def test_unstructured_http_errors(make_client, status):
    instance = make_client(lambda _: httpx.Response(status, text="unavailable"))
    with pytest.raises(VatTransportError, match=str(status)):
        instance.search(NIP, "nip", DATE)


def test_network_failure_no_retry(make_client):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(VatTransportError, match="offline"):
        make_client(handler).search(NIP, "nip", DATE)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b"null", b'{"result":null}', b'{"result":{}}'])
def test_malformed_response(make_client, body):
    with pytest.raises(VatProtocolError):
        make_client(lambda _: httpx.Response(200, content=body)).search(NIP, "nip", DATE)


@pytest.mark.parametrize("field,value", [("subject", []), ("requestId", None), ("requestDateTime", "")])
def test_invalid_single_result(make_client, field, value):
    payload = fixture("search_result")
    payload["result"][field] = value
    with pytest.raises(VatProtocolError):
        make_client(lambda _: httpx.Response(200, json=payload)).search(NIP, "nip", DATE)


@pytest.mark.parametrize("entries", [None, [None], [{"identifier": NIP}], [{"identifier": NIP, "error": {}}], [{"identifier": NIP, "subjects": []}, {"identifier": "unexpected", "subjects": []}], []])
def test_malformed_or_incomplete_batch_is_not_no_matches(make_client, entries):
    payload = fixture("batch_result")
    payload["result"]["entries"] = entries
    with pytest.raises(VatProtocolError):
        make_client(lambda _: httpx.Response(200, json=payload)).search_bulk([NIP], "nip", DATE)


@pytest.mark.parametrize("value", [False, "", "UNKNOWN", None])
def test_invalid_check_answer_is_protocol_error(make_client, value):
    payload = fixture("check_result")
    payload["result"]["accountAssigned"] = value
    with pytest.raises(VatProtocolError):
        make_client(lambda _: httpx.Response(200, json=payload)).check_bank_account(NIP, "nip", ACCOUNT, DATE)


def test_response_size_guard(make_client, monkeypatch):
    monkeypatch.setattr(module, "_MAX_RESPONSE_BYTES", 32)
    with pytest.raises(VatProtocolError, match="maximum"):
        make_client(lambda _: httpx.Response(200, content=b" " * 33)).search(NIP, "nip", DATE)


@pytest.mark.parametrize("kwargs", [{"environment": "invalid"}, {"timeout": 0}, {"timeout": -1}, {"timeout": float("inf")}, {"timeout": float("nan")}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        VatConfig(**kwargs)


def test_context_manager_closes_http(make_client):
    with make_client(lambda _: httpx.Response(200, json=fixture("search_result"))) as instance:
        assert not instance._http.is_closed
    assert instance._http.is_closed
