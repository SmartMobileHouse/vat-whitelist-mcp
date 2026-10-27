"""Typed exceptions shared across the package.

Kept in a dedicated module so both ``client`` and ``parse`` can raise them
without a circular import.
"""

from __future__ import annotations


class RegonError(Exception):
    """Base error for all REGON/BIR client failures."""


class RegonAuthError(RegonError):
    """Login failed — e.g. an invalid or missing USER_KEY."""


class RegonSessionError(RegonError):
    """The BIR session was rejected or has expired; a re-login may recover."""


class RegonTransportError(RegonError):
    """A network/HTTP-level failure talking to the BIR endpoint."""


class RegonProtocolError(RegonError):
    """The service returned a malformed, oversized, or unexpected response."""
