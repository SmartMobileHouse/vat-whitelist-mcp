"""SOAP 1.2 + WS-Addressing envelope construction for the GUS BIR1 service.

The BIR1 endpoint is a WCF service that requires:
  * SOAP 1.2 with the action carried in the Content-Type header, and
  * WS-Addressing ``To`` / ``Action`` headers in the SOAP header.

The session id returned by ``Zaloguj`` is *not* part of the SOAP body — it is
sent as a plain HTTP header named ``sid`` on subsequent calls (see client.py).
"""

from __future__ import annotations

# WS-Addressing action prefix (interface name), shared by every operation.
NS_ACTION = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl"

_TEMPLATE = (
    '<soap:Envelope '
    'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:ns="http://CIS/BIR/PUBL/2014/07" '
    'xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract" '
    'xmlns:wsa="http://www.w3.org/2005/08/addressing">'
    "<soap:Header>"
    "<wsa:To>{endpoint}</wsa:To>"
    "<wsa:Action>{action_ns}/{action}</wsa:Action>"
    "</soap:Header>"
    "<soap:Body>{body}</soap:Body>"
    "</soap:Envelope>"
)


def build_envelope(endpoint: str, action: str, body: str) -> str:
    """Wrap a SOAP body fragment in a full addressed SOAP 1.2 envelope."""
    return _TEMPLATE.format(
        endpoint=endpoint, action_ns=NS_ACTION, action=action, body=body
    )
