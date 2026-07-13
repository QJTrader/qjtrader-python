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
from .autotools import REGISTRY as AUTO_TOOLS, Scalper, make_auto_tool
from .backtest import BacktestReport, run_backtest, synthetic_bars
from .l2backtest import L2Context, run_l2_backtest, synthetic_l2_events
from .client import (
    Client,
    MARKET_DATA_SCOPE,
    ORDERS_SCOPE,
)
from .errors import AuthError, ConnectionClosed, QJError, TokenError
from .market_data import MarketData
from .orders import Orders
from .rest import RestClient
from .run import LiveContext, Supervisor, load_strategy, run_strategy_live
from .runner import RunRegistry
from .runner_service import RunnerService
from .strategy import Context, PositionBook, Strategy

__all__ = [
    "Client",
    "MarketData",
    "Orders",
    "RestClient",
    "QJError",
    "TokenError",
    "AuthError",
    "ConnectionClosed",
    "MARKET_DATA_SCOPE",
    "ORDERS_SCOPE",
    # strategy contract + run venues (§10)
    "Strategy",
    "Context",
    "PositionBook",
    "run_backtest",
    "synthetic_bars",
    "BacktestReport",
    "run_l2_backtest",
    "synthetic_l2_events",
    "L2Context",
    "Supervisor",
    "LiveContext",
    "load_strategy",
    "run_strategy_live",
    "RunRegistry",
    "RunnerService",
    "Scalper",
    "make_auto_tool",
    "AUTO_TOOLS",
    "__version__",
]
