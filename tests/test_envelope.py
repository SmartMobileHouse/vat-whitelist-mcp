"""Guards for the SOAP request serialization.

The search parameter elements (Nip/Regon/Krs) must sit in the WCF DataContract
namespace. An earlier build used the wrong namespace, which WCF silently dropped
— every search returned empty with no error. These tests lock the shape down.
"""

from vat_whitelist_mcp.client import _build_search_params
from vat_whitelist_mcp.envelopes import build_envelope

# The one true namespace for search parameters (verified against the live API).
DATA_CONTRACT_NS = "http://CIS/BIR/PUBL/2014/07/DataContract"


def test_envelope_declares_datacontract_namespace():
    env = build_envelope("https://example/svc", "DaneSzukajPodmioty", "<x/>")
    assert f'xmlns:dat="{DATA_CONTRACT_NS}"' in env
    # The previously-wrong namespace must never reappear.
    assert "DaneOsobowe" not in env


def test_single_search_param_uses_dat_prefix():
    assert _build_search_params(nip="5261040828") == "<dat:Nip>5261040828</dat:Nip>"
    assert _build_search_params(regon="000331501") == "<dat:Regon>000331501</dat:Regon>"


def test_batch_search_param_joins_with_commas():
    assert (
        _build_search_params(nips=["5261040828", "7740001454"])
        == "<dat:Nipy>5261040828,7740001454</dat:Nipy>"
    )


def test_search_params_reject_mixed_or_empty():
    import pytest

    with pytest.raises(ValueError):
        _build_search_params()
    with pytest.raises(ValueError):
        _build_search_params(nip="1", regon="2")
