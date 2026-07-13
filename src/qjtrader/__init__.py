"""qjtrader — the official Python client for the QJ Trader AI Trading APIs.

Stream real-time Canadian market data and send orders over one authenticated
connection. Get a free sandbox key (no approval) at https://console.qjtrader.ai
and set ``QJ_CLIENT_ID`` / ``QJ_CLIENT_SECRET``:

    import qjtrader
    client = qjtrader.Client()
    with client.orders() as oe:
        print(oe.order_and_wait(sym="MX:CRAU26", side="buy", qty=1,
                                price=97.00, account="SIM", tif="ioc"))

Docs: https://docs.qjtrader.ai/docs/ai
"""
from __future__ import annotations

from ._version import __version__
from .client import (
    Client,
    MARKET_DATA_SCOPE,
    ORDERS_SCOPE,
)
from .errors import AuthError, ConnectionClosed, QJError, TokenError
from .market_data import MarketData
from .orders import Orders

__all__ = [
    "Client",
    "MarketData",
    "Orders",
    "QJError",
    "TokenError",
    "AuthError",
    "ConnectionClosed",
    "MARKET_DATA_SCOPE",
    "ORDERS_SCOPE",
    "__version__",
]
