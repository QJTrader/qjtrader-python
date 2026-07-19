"""The top-level entry point: :class:`Client`.

    import qjtrader
    client = qjtrader.Client()          # reads QJ_CLIENT_ID / QJ_CLIENT_SECRET from env

    with client.market_data() as md:
        md.subscribe(["CA:RY", "MX:CRAU26", "US:@ESU26"])
        for msg in md.messages(timeout=30):
            print(msg["type"], msg.get("symbol"))

    with client.orders() as oe:
        fill = oe.order_and_wait(sym="MX:CRAU26", side="buy", qty=1,
                                 price=97.00, account="SIM", tif="ioc")
        print(fill)

The same code runs against a **sandbox** or a **production** credential — the
credential decides which, server-side. Get a free sandbox key (no approval) at
https://gateway.qjtrader.ai.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, TypedDict

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


class PositionDetail(TypedDict, total=False):
    """One canonical symbol's broker-truth split from ``positions_detail``.

    ``total_qty = broker_qty + fill_qty`` — the desktop ``InitVolume + NetVolume``.
    ``broker_qty`` is 0 on a simulated plane. ``price``/``currency``/``account``/
    ``source`` are present only when a broker row backs the symbol.
    """
    broker_qty: int
    fill_qty: int
    total_qty: int
    price: Optional[float]
    currency: Optional[str]
    account: Optional[str]
    source: Optional[str]


class AccountFinancial(TypedDict, total=False):
    """Broker morning account fields, keyed by trading account.

    ``account_value`` supports Desktop-style capital monitoring. It is not
    guaranteed spendable cash or buying power; those remain ``None`` unless a
    broker supplies an authoritative value.
    """
    account_value: Optional[float]
    currency: Optional[str]
    source: Optional[str]
    margin_or_excess: Optional[float]
    current_trade_balance: Optional[float]
    current_settlement_balance: Optional[float]
    market_value: Optional[float]
    loan_value: Optional[float]
    broker_capital_required: Optional[float]
    account_status: Optional[str]
    activity_date: Optional[str]
    cash_available: Optional[float]
    buying_power: Optional[float]
    status: Optional[str]


class PositionsEnvelope(TypedDict, total=False):
    """Return shape of :meth:`Client.positions` (``GET /api/v1/positions``).

    Always present: ``type``, ``user``, ``envelope`` (limit caps), ``positions``
    (flat fill-only ``symbol -> net int``, back-compat), ``orders_env`` (plane).
    Present only on a real plane with the broker feed wired: ``positions_detail``,
    ``admserv_limits``, ``capital_required``, ``broker_asof``, ``broker_synced_at``.
    """
    type: str
    user: str
    envelope: Dict[str, Any]
    positions: Dict[str, int]
    tag_positions: Dict[str, int]
    orders_env: Optional[str]
    positions_detail: Dict[str, PositionDetail]
    positions_by_account: Dict[str, Dict[str, PositionDetail]]
    account_financials: Dict[str, AccountFinancial]
    admserv_limits: Dict[str, Any]
    capital_required: Dict[str, Any]
    broker_asof: Optional[str]
    broker_synced_at: Optional[str]


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
                "https://gateway.qjtrader.ai"
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

    @classmethod
    def from_env_file(cls, file: str | os.PathLike[str], **overrides: Any) -> "Client":
        """Create a client from an ACL-restricted machine credential file.

        The file is parsed directly and never sourced by a shell or copied into
        ``os.environ``. Human Gateway usernames, passwords, MFA codes and admin
        approval do not belong in this file.
        """
        from .credentials import load_credentials_file
        values = load_credentials_file(file)
        options: dict[str, Any] = {
            "client_id": values["QJ_CLIENT_ID"],
            "client_secret": values["QJ_CLIENT_SECRET"],
            "token_url": values.get("QJ_TOKEN_URL"),
            "data_host": values.get("QJ_DATA_HOST"),
            "data_port": int(values["QJ_DATA_PORT"]) if values.get("QJ_DATA_PORT") else None,
            "orders_host": values.get("QJ_ORDERS_HOST"),
            "orders_port": int(values["QJ_ORDERS_PORT"]) if values.get("QJ_ORDERS_PORT") else None,
            "data_rest_port": int(values["QJ_DATA_REST_PORT"]) if values.get("QJ_DATA_REST_PORT") else None,
            "orders_rest_port": int(values["QJ_ORDERS_REST_PORT"]) if values.get("QJ_ORDERS_REST_PORT") else None,
            "ca_file": values.get("QJ_CA_FILE"),
        }
        options.update({key: value for key, value in overrides.items() if value is not None})
        return cls(**options)

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

    def session_info(self) -> dict[str, Any]:
        """Return server-authoritative environments and this key's active access.

        This deliberately probes both authenticated stream handshakes instead of
        inferring safety from a local ``QJ_ENV`` declaration. Callers may compare
        a local declaration for stale configuration, but the server values are
        the authority. ``data_session.data_products`` and
        ``orders_session.order_products/order_accounts`` expose the restricted
        key subset enforced by the two gateways.
        """
        info: dict[str, Any] = {"credential": self._client_id}
        try:
            with self.market_data() as md:
                info["authenticated_user"] = md.user
                info["data_environment"] = md.environment
                info["data_session"] = dict(md.auth_info)
        except QJError as exc:
            info["data_error"] = str(exc)
        try:
            with self.orders() as oe:
                info.setdefault("authenticated_user", oe.user)
                info["orders_environment"] = oe.environment
                info["authority_version"] = oe.authority_version
                info["orders_session"] = dict(oe.auth_info)
        except QJError as exc:
            info["orders_error"] = str(exc)
        return info

    def search_universe(self, query: str = "", limit: int = 50) -> dict[str, Any]:
        """Search symbols visible to this credential and explain their capabilities."""
        from .universe import search_symbols
        symbols = self.data_rest().get("/api/v1/symbols").get("symbols", [])
        session = self.session_info()
        return {
            "query": query,
            "source": "credential-visible symbols",
            "data_environment": session.get("data_environment"),
            "orders_environment": session.get("orders_environment"),
            "instruments": search_symbols(
                list(map(str, symbols)), query, limit=limit,
                data_environment=session.get("data_environment"),
                orders_environment=session.get("orders_environment"),
            ),
        }

    def describe_instrument(self, symbol: str) -> dict[str, Any]:
        """Explain a symbol in the context of this credential's current authority."""
        from .universe import describe_instrument
        session = self.session_info()
        return describe_instrument(
            symbol,
            data_environment=session.get("data_environment"),
            orders_environment=session.get("orders_environment"),
        )

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
        """Historical OHLCV bars with explicit provenance.

        ``source`` is ``synthetic`` in sandbox, ``recorded`` for captured
        production observations, or ``unavailable``. Production never falls
        back to generated bars.
        """
        return self.data_rest().get("/api/v1/history", {
            "symbol": symbol, "interval": interval, "from": frm, "to": to, "limit": limit})

    def stats(self, symbol: str, interval: str = "1m", window: float = 3600.0) -> dict:
        """Server-computed digest plus the same history provenance fields."""
        return self.data_rest().get("/api/v1/stats", {
            "symbol": symbol, "interval": interval, "window": window})

    def quote(self, symbol: str, timeout: float = 10.0) -> dict:
        """Return a normalized live top-of-book without hand-parsing snapshots."""
        with self.market_data() as md:
            return md.quote(symbol, timeout=timeout)

    def chain(self, underlying: str, expiry: str, at=None) -> dict:
        """Options chain snapshot for an ``underlying`` at a given ``expiry``.

        ``expiry`` is the expiry MONTH as ``YYYYMM`` (e.g. ``"202608"`` for Aug
        2026) — the server derives the third-Friday expiry day itself. Common
        spellings (``"2026-08-21"``, ``"20260821"``, ``"26AUG21"``) are
        normalized for you. Discover valid months with :meth:`expiries` or
        :func:`qjtrader.front_expiry_month`. Returns the latest snapshot, or the
        nearest at/before ``at``."""
        from .calendar import normalize_expiry_month
        return self.data_rest().get("/api/v1/chain", {
            "underlying": underlying, "expiry": normalize_expiry_month(expiry), "at": at})

    def chain_stats(self, underlying: str, expiry: str, at=None) -> dict:
        """OI concentration, volume, put/call ratio and IV-skew digest."""
        from .calendar import normalize_expiry_month
        return self.data_rest().get("/api/v1/chain/stats", {
            "underlying": underlying, "expiry": normalize_expiry_month(expiry), "at": at})

    def expiries(self, underlying: str) -> dict:
        """Upcoming valid chain expiry months (``YYYYMM``) for an underlying — so
        you pass a real ``expiry`` to :meth:`chain` instead of guessing a date."""
        return self.data_rest().get("/api/v1/expiries", {"underlying": underlying})

    def recordings(self, symbol: str) -> dict:
        """Which tick-history dates exist for a symbol (honest coverage)."""
        return self.data_rest().get("/api/v1/recordings", {"symbol": symbol})

    def recording_status(self, symbol: str) -> dict:
        """How QJ remembers this symbol: ready, observed now, or continuous.

        Lightweight bars are captured automatically while a production symbol
        is observed. A continuous pin keeps a standing subscription and richer
        market-event capture after the user's apps disconnect.
        """
        return self.data_rest().get("/api/v1/recording", {"symbol": symbol})

    def recording_pins(self) -> dict:
        """List this key's production symbols kept in continuous memory."""
        return self.data_rest().get("/api/v1/recording/pins")

    def pin_recording(self, symbol: str) -> dict:
        """Keep recording a production symbol when every user app disconnects."""
        return self.data_rest().put("/api/v1/recording/pin", {"symbol": symbol})

    def unpin_recording(self, symbol: str) -> dict:
        """Return a symbol to automatic, observation-driven recording."""
        return self.data_rest().delete("/api/v1/recording/pin", {"symbol": symbol})

    def events(self, since=None, limit: int = 200) -> dict:
        """Cross-order journal history (blotter/replay/post-trade analysis)."""
        return self.orders_rest().get("/api/v1/events", {"since": since, "limit": limit})

    def prove(self, symbol: str = "CA:RY", *, account: str = "SIM",
              timeout: float = 10.0) -> dict:
        """Run quote → resting order → cancel → journal as one sandbox proof."""
        quote = self.quote(symbol, timeout=timeout)
        bid = quote.get("bid")
        if bid is None:
            raise QJError(f"no bid received for {symbol}")
        price = round(float(bid) * .85, 2)
        lifecycle = []
        with self.orders() as oe:
            cid = oe.order(sym=symbol, side="buy", qty=1, price=price, account=account)
            for msg in oe.updates(timeout=timeout):
                if msg.get("cid") == cid:
                    lifecycle.append(msg)
                    if msg.get("status") == "new":
                        break
            cancel_cid = oe.cancel(cid)
            for msg in oe.updates(timeout=timeout):
                if msg.get("cid") == cid or msg.get("orig_cid") == cid:
                    lifecycle.append(msg)
                    if msg.get("status") == "canceled":
                        break
        journal = self.events(limit=50)
        return {"symbol": symbol, "quote": quote, "cid": cid,
                "cancel_cid": cancel_cid, "lifecycle": lifecycle,
                "journal": [e for e in journal.get("events", []) if e.get("cid") == cid]}

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

    def positions(self) -> "PositionsEnvelope":
        """Agent-account envelope + live positions per symbol/strategy-tag (§10.5).

        Besides the envelope limits and the flat fill-only ``positions`` map (kept
        for back-compat), on a **real**-plane credential with the broker feed wired
        the response also carries the broker-truth split (oms-positions-plan.md
        §3.4): ``positions_detail`` maps each canonical symbol to
        ``{broker_qty, fill_qty, total_qty}`` — the desktop formula
        ``TotalVolume = InitVolume (broker start-of-day) + NetVolume (today's fills)``
        — plus ``admserv_limits`` (the hard floor/ceiling risk caps),
        ``capital_required``, ``broker_asof`` and ``broker_synced_at``.
        ``positions_by_account`` preserves the account split and
        ``account_financials`` carries broker morning account values. Account
        value is not spendable cash or buying power; those fields remain empty
        unless the broker supplies an authoritative value.

        ``orders_env`` reports the credential's order plane
        (``sandbox``/``paper``/``shadow``/``real``, or ``None`` on a legacy real
        credential). On a **simulated** plane there is no broker book: the response
        omits ``admserv_limits``/``capital_required``/``broker_asof`` and
        ``positions_detail`` is fill-only (``broker_qty`` 0). Don't chase a
        "missing broker data" bug for a sandbox credential — that's the design.
        """
        return self.orders_rest().get("/api/v1/positions")

    def get_scenario(self) -> dict:
        """Current sandbox market scenario (halt/fast/gap/normal)."""
        return self.data_rest().get("/api/v1/scenario")

    def set_scenario(self, name: str, symbol: str | None = None,
                     seconds: float = 30.0) -> dict:
        """Set a sandbox market scenario (sandbox credentials only). §10.4."""
        return self.data_rest().post("/api/v1/scenario",
                                     {"name": name, "symbol": symbol, "seconds": seconds})
