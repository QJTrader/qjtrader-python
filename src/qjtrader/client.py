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
from .rest import RestClient

# Public defaults (override via args or QJ_* env vars).
DEFAULT_TOKEN_URL = (
    "https://qj-bridge-209866815475.auth.ca-central-1.amazoncognito.com/oauth2/token"
)
DEFAULT_DATA_HOST = "data-feed.qjtrader.ai"
DEFAULT_DATA_PORT = 7000
DEFAULT_ORDERS_HOST = "orders.qjtrader.ai"
DEFAULT_ORDERS_PORT = 7001
# WS/REST gateway ports (history/stats/chain on data, events/orders on orders).
DEFAULT_DATA_REST_PORT = 8443
DEFAULT_ORDERS_REST_PORT = 8443

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
                 data_rest_port: int | None = None, orders_rest_port: int | None = None,
                 ca_file: str | None = None, verify: bool = True,
                 rest_opener=None) -> None:
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
        self._data_rest_port = data_rest_port or int(
            os.environ.get("QJ_DATA_REST_PORT", DEFAULT_DATA_REST_PORT))
        self._orders_rest_port = orders_rest_port or int(
            os.environ.get("QJ_ORDERS_REST_PORT", DEFAULT_ORDERS_REST_PORT))
        self._ca_file = ca_file or os.environ.get("QJ_CA_FILE") or None
        self._verify = verify
        self._rest_opener = rest_opener  # test hook: inject a fake HTTP fetcher

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

    # ------------------------------------------------------------ REST reads
    def data_rest(self, opener=None) -> RestClient:
        """REST client for the data gateway (history/stats/chain/recordings)."""
        return RestClient(
            f"https://{self._data_host}:{self._data_rest_port}",
            self._token_source(MARKET_DATA_SCOPE),
            ca_file=self._ca_file, verify=self._verify,
            opener=opener or self._rest_opener)

    def orders_rest(self, opener=None) -> RestClient:
        """REST client for the orders gateway (events journal, open orders)."""
        return RestClient(
            f"https://{self._orders_host}:{self._orders_rest_port}",
            self._token_source(ORDERS_SCOPE),
            ca_file=self._ca_file, verify=self._verify,
            opener=opener or self._rest_opener)

    def history(self, symbol: str, interval: str = "1m", frm=None, to=None,
                limit: int = 500) -> dict:
        """Historical OHLCV bars for a symbol (synthetic for sandbox creds)."""
        return self.data_rest().get("/api/v1/history", {
            "symbol": symbol, "interval": interval, "from": frm, "to": to, "limit": limit})

    def stats(self, symbol: str, interval: str = "1m", window: float = 3600.0) -> dict:
        """Server-computed digest (VWAP, spread, volume, realized vol) for a symbol."""
        return self.data_rest().get("/api/v1/stats", {
            "symbol": symbol, "interval": interval, "window": window})

    def chain(self, underlying: str, expiry: str, at=None) -> dict:
        """Options chain snapshot (latest, or nearest at/before `at`)."""
        return self.data_rest().get("/api/v1/chain", {
            "underlying": underlying, "expiry": expiry, "at": at})

    def recordings(self, symbol: str) -> dict:
        """Which tick-history dates exist for a symbol (honest coverage)."""
        return self.data_rest().get("/api/v1/recordings", {"symbol": symbol})

    def events(self, since=None, limit: int = 200) -> dict:
        """Cross-order journal history (blotter/replay/post-trade analysis)."""
        return self.orders_rest().get("/api/v1/events", {"since": since, "limit": limit})

    def order_snapshot(self) -> dict:
        """Open orders + session state on this credential (read-only)."""
        return self.orders_rest().get("/api/v1/orders")

    def intent_diff(self, tag_a: str, tag_b: str, limit: int = 1000) -> dict:
        """Diff two strategy versions'/runs' order intents from the journal (§8
        shadow regression / L1). Tags are version-scoped (`<name>.<ver>`), so this
        compares e.g. a new version running in shadow against the live one before
        promoting it — decision-for-decision, flagging any divergence."""
        from .intents import intent_diff as _diff
        events = (self.events(limit=limit) or {}).get("events") or []
        return _diff(events, tag_a, tag_b)

    def positions(self) -> dict:
        """Agent-account envelope + live positions per symbol/strategy-tag (§10.5)."""
        return self.orders_rest().get("/api/v1/positions")

    def get_scenario(self) -> dict:
        """Current sandbox market scenario (halt/fast/gap/normal)."""
        return self.data_rest().get("/api/v1/scenario")

    def set_scenario(self, name: str, symbol: str | None = None,
                     seconds: float = 30.0) -> dict:
        """Set a sandbox market scenario (sandbox credentials only). §10.4."""
        return self.data_rest().post("/api/v1/scenario",
                                     {"name": name, "symbol": symbol, "seconds": seconds})
