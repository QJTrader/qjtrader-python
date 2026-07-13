"""Exceptions raised by the qjtrader client."""
from __future__ import annotations


class QJError(Exception):
    """Base class for all qjtrader errors."""


class TokenError(QJError):
    """Failed to obtain an OAuth2 access token (bad credentials, network, scope)."""


class AuthError(QJError):
    """The service rejected the connection's auth handshake."""


class ConnectionClosed(QJError):
    """The server closed the stream."""
