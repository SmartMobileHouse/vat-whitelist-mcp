"""Typed failures returned by the VAT White List client."""


class VatError(Exception):
    """Base error for VAT White List client failures."""


class VatTransportError(VatError):
    """A network or HTTP failure without a structured API error."""


class VatProtocolError(VatError):
    """A malformed, oversized, or unexpected API response."""


class VatApiError(VatError):
    """An upstream API failure, retaining its code, message and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"{code}: {message} (HTTP {status_code})")
