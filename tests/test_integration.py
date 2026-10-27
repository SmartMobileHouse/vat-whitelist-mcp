"""Live tests against the GUS BIR endpoint (deselected unless opted in).

    REGON_RUN_NETWORK=1 uv run pytest -m network          # session lifecycle (test env)
    REGON_PROD_KEY=<key> uv run pytest -m network          # positive control (live data)

The test database is anonymized, so the test-env case validates the session
lifecycle and response *shape* — never data content. The prod positive-control
asserts a stable, well-known entity actually resolves, which is what catches a
malformed search request (an earlier bug that returned empty for everything).
"""

import os

import pytest

from vat_whitelist_mcp.client import RegonClient, RegonConfig

pytestmark = pytest.mark.network

_RUN = os.getenv("REGON_RUN_NETWORK") == "1"
_PROD_KEY = os.getenv("REGON_PROD_KEY")


@pytest.mark.skipif(not _RUN, reason="set REGON_RUN_NETWORK=1 to run live tests")
def test_login_lifecycle_against_test_env():
    with RegonClient(RegonConfig(environment="test")) as client:
        sid = client.login()
        assert isinstance(sid, str) and len(sid) >= 10
        # A valid (possibly empty) result set — shape, not content.
        assert isinstance(client.search(regon="000331501"), list)
        assert client.logout() is True


@pytest.mark.skipif(not _PROD_KEY, reason="set REGON_PROD_KEY to run the prod positive-control")
def test_known_entity_resolves_on_prod():
    with RegonClient(RegonConfig(api_key=_PROD_KEY, environment="prod")) as client:
        rows = client.search(regon="000331501")
        assert rows, "search returned no rows for a known REGON — request likely malformed"
        assert "GŁÓWNY URZĄD STATYSTYCZNY" in rows[0]["name"]
