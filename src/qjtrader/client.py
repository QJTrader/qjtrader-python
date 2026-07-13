"""The top-level entry point: :class:`Client`.

    import qjtrader
    client = qjtrader.Client()          # reads QJ_CLIENT_ID / QJ_CLIENT_SECRET from env

    with client.market_data() as md:
        md.subscribe(["CA:RY", "MX:CRAU26"])
        for msg in md.messages(timeout=30):
            print(msg["type"], msg.get("symbol"))

    with client.orders() as oe:
        fill = oe.order_and_wait(sym="MX:CRAU26", side="buy", qty=1,
                                 price=97.00, account="SIM", tif="ioc")
        print(fill)

The same code runs against a **sandbox** or a **production** credential — the
credential decides which, server-side. Get a free sandbox key (no approval) at
https://console.qjtrader.ai.
"""
from __future__ import annotations

import os

from .auth import TokenSource
from .errors import QJError
from .market_data import MarketData
from .orders import Orders

# Public defaults (override via args or QJ_* env vars).
DEFAULT_TOKEN_URL = (
    "https://qj-bridge-209866815475.auth.ca-central-1.amazoncognito.com/oauth2/token"
)
DEFAULT_DATA_HOST = "data-feed.qjtrader.ai"
DEFAULT_DATA_PORT = 7000
DEFAULT_ORDERS_HOST = "orders.qjtrader.ai"
DEFAULT_ORDERS_PORT = 7001

MARKET_DATA_SCOPE = "qj-data-feed/market-data"
ORDERS_SCOPE = "qj-data-feed/orders"


class Client:
    """Holds your credential and connection settings; opens API connections.

    Credentials default to the ``QJ_CLIENT_ID`` / ``QJ_CLIENT_SECRET`` environment
    variables so you never put secrets on the command line. Endpoints default to
    the public QJ hosts and can be overridden per-arg or via ``QJ_TOKEN_URL`` /
    ``QJ_DATA_HOST`` / ``QJ_ORDERS_HOST``.

    ``ca_file`` pins a specific CA/cert (pilot users are given one out-of-band for
    the order endpoint); leave it unset for standard public-CA validation.
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 *, token_url: str | None = None,
                 data_host: str | None = None, data_port: int | None = None,
                 orders_host: str | None = None, orders_port: int | None = None,
                 ca_file: str | None = None, verify: bool = True) -> None:
        self._client_id = client_id or os.environ.get("QJ_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("QJ_CLIENT_SECRET")
        if not self._client_id or not self._client_secret:
            raise QJError(
                "client_id/client_secret required — pass them to Client(...) or set "
                "QJ_CLIENT_ID and QJ_CLIENT_SECRET. Get a free sandbox key at "
                "https://console.qjtrader.ai"
            )
        self._token_url = token_url or os.environ.get("QJ_TOKEN_URL") or DEFAULT_TOKEN_URL
        self._data_host = data_host or os.environ.get("QJ_DATA_HOST") or DEFAULT_DATA_HOST
        self._data_port = data_port or int(os.environ.get("QJ_DATA_PORT", DEFAULT_DATA_PORT))
        self._orders_host = orders_host or os.environ.get("QJ_ORDERS_HOST") or DEFAULT_ORDERS_HOST
        self._orders_port = orders_port or int(os.environ.get("QJ_ORDERS_PORT", DEFAULT_ORDERS_PORT))
        self._ca_file = ca_file or os.environ.get("QJ_CA_FILE") or None
        self._verify = verify

    def _token_source(self, scope: str) -> TokenSource:
        return TokenSource(self._token_url, self._client_id, self._client_secret, scope)

    def market_data(self) -> MarketData:
        """Open an authenticated Market Data connection."""
        return MarketData(
            self._token_source(MARKET_DATA_SCOPE), self._data_host, self._data_port,
            ca_file=self._ca_file, verify=self._verify,
        ).connect()  # type: ignore[return-value]

    def orders(self) -> Orders:
        """Open an authenticated Order Entry connection."""
        return Orders(
            self._token_source(ORDERS_SCOPE), self._orders_host, self._orders_port,
            ca_file=self._ca_file, verify=self._verify,
        ).connect()  # type: ignore[return-value]

    def token(self, scope: str = MARKET_DATA_SCOPE) -> str:
        """Mint a raw access token for a scope (handy for the WebSocket/REST paths)."""
        return self._token_source(scope).token()
