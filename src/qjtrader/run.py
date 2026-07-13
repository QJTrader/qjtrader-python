"""The strategy supervisor — run-venue rung 3 (plan §10.3): ``qjtrader run``.

A thin, deterministic host for a strategy against a **live or paper** credential.
It owns the client, injects the context, tags every order with the strategy name
(so the journal groups by strategy — the blotter/replay get it for free), and on
SIGINT cancels everything and calls ``on_stop``. The *same strategy file* also
runs in the backtest engine (``backtest.run_backtest``); this module is where it
meets a real order path.

The dispatch core (``Supervisor`` + ``LiveContext``) is transport-agnostic and
fully unit-testable with fake connections; ``run_strategy_live`` wires the real
market-data and order streams behind it.
"""
from __future__ import annotations

import importlib.util
import queue
import threading
import time
from typing import Any, Iterable, Iterator

from .errors import QJError
from .strategy import Context, PositionBook, Strategy

_FILL_STATUSES = ("partial", "filled")


# ---------------------------------------------------------------- strategy load
def load_strategy(path: str) -> Strategy:
    """Import a .py file and instantiate its ``Strategy`` subclass."""
    spec = importlib.util.spec_from_file_location("qj_user_strategy", path)
    if spec is None or spec.loader is None:
        raise QJError(f"cannot load strategy file: {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # surface user code errors clearly
        raise QJError(f"error importing {path}: {e}") from e
    for obj in vars(mod).values():
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
            return obj()
    raise QJError(f"no Strategy subclass found in {path}")


# ------------------------------------------------------------------- context
class LiveContext(Context):
    """Context backed by a real order-entry connection (duck-typed: needs
    ``order``/``cancel``/``replace``/``cancel_all``)."""

    def __init__(self, orders: Any, strategy_tag: str = "strat",
                 account: str = "", clock=time.time) -> None:
        self._oe = orders
        self.tag = strategy_tag
        self._account = account
        self._clock = clock
        self.params: dict[str, Any] = {}
        self._seq = 0
        self.orders: dict[str, dict[str, Any]] = {}
        self.books: dict[str, PositionBook] = {}
        self.marks: dict[str, float] = {}
        self._quotes: dict[str, dict[str, Any]] = {}

    def param(self, key, default=None):
        return self.params.get(key, default)

    def now(self):
        return self._clock()

    def log(self, *args):
        print(f"[{self.tag}]", *args)

    def _cid(self, cid):
        if cid:
            return cid
        self._seq += 1
        return f"{self.tag}-{self._seq}"  # tag prefix => journal groups by strategy

    def _record(self, cid, sym, side, qty, price, tif):
        self.orders[cid] = {"cid": cid, "sym": sym, "side": side, "qty": qty,
                            "price": price, "tif": tif}

    def buy(self, sym, qty, price, *, tif="day", account="", cid=None):
        cid = self._cid(cid)
        self._oe.order(sym=sym, side="buy", qty=qty, price=price, tif=tif,
                       account=account or self._account, cid=cid)
        self._record(cid, sym, "buy", qty, price, tif)
        return cid

    def sell(self, sym, qty, price, *, tif="day", account="", cid=None):
        cid = self._cid(cid)
        self._oe.order(sym=sym, side="sell", qty=qty, price=price, tif=tif,
                       account=account or self._account, cid=cid)
        self._record(cid, sym, "sell", qty, price, tif)
        return cid

    def cancel(self, cid):
        self._oe.cancel(cid)

    def replace(self, cid, *, qty=None, price=None):
        self._oe.replace(cid, qty=qty, price=price)

    def position(self, sym):
        return self.books[sym].net if sym in self.books else 0

    def positions(self):
        return {s: b.net for s, b in self.books.items() if b.net}

    def quote(self, sym):
        return self._quotes.get(sym)

    # applied by the supervisor as exec reports arrive
    def _apply_fill(self, cid, qty, price):
        o = self.orders.get(cid)
        side = o["side"] if o else "buy"
        sym = o["sym"] if o else cid
        self.books.setdefault(sym, PositionBook()).apply(side, qty, price)


# ------------------------------------------------------------------ supervisor
class Supervisor:
    """Dispatches merged (kind, msg) events to a strategy. Transport-agnostic."""

    def __init__(self, strategy: Strategy, ctx: LiveContext) -> None:
        self.strategy = strategy
        self.ctx = ctx

    def start(self) -> None:
        self.strategy.on_start(self.ctx)

    def dispatch(self, kind: str, msg: dict[str, Any] | None) -> None:
        if kind == "timer":
            self.strategy.on_timer(self.ctx)
            return
        if msg is None:
            return
        if kind == "md":
            mtype = msg.get("type")
            sym = msg.get("symbol")
            if mtype == "quote":
                data = msg.get("data") or {}
                if sym:
                    self.ctx._quotes[sym] = data
                self.strategy.on_quote(self.ctx, msg)
            elif mtype in ("level2", "snapshot"):
                self.strategy.on_depth(self.ctx, msg)
            elif mtype == "trade":
                px = (msg.get("data") or {}).get("price")
                if sym and px is not None:
                    self.ctx.marks[sym] = px
                self.strategy.on_trade(self.ctx, msg)
        elif kind == "oe":
            if msg.get("type") == "exec" and msg.get("status") in _FILL_STATUSES:
                self.ctx._apply_fill(msg.get("cid"), msg.get("last_qty") or 0,
                                     msg.get("last_px") or 0.0)
            self.strategy.on_fill(self.ctx, msg)

    def run(self, events: Iterable[tuple[str, Any]]) -> None:
        self.start()
        try:
            for kind, msg in events:
                self.dispatch(kind, msg)
        finally:
            self.stop()

    def stop(self) -> None:
        try:
            self.strategy.on_stop(self.ctx)
        finally:
            try:
                self.ctx._oe.cancel_all()   # never leave orders working on exit
            except Exception:
                pass


# ------------------------------------------------------------- live event merge
def merge_streams(md: Any, oe: Any, *, timer_s: float = 1.0,
                  stop: threading.Event | None = None,
                  window_s: float = 3600.0) -> Iterator[tuple[str, Any]]:
    """Merge market-data and order-update streams into one (kind, msg) iterator,
    emitting a ``("timer", None)`` tick every `timer_s` seconds of quiet.

    Two daemon threads pump the SDK's blocking iterators into a queue; this is the
    live adapter behind ``run_strategy_live`` (exercised against real gateways).
    """
    stop = stop or threading.Event()
    q: "queue.Queue[tuple[str, Any]]" = queue.Queue()

    def pump(kind: str, src_factory) -> None:
        try:
            while not stop.is_set():
                for msg in src_factory():
                    q.put((kind, msg))
                    if stop.is_set():
                        return
        except Exception:
            pass

    threading.Thread(target=pump, args=("md", lambda: md.messages(timeout=window_s)),
                     daemon=True).start()
    threading.Thread(target=pump, args=("oe", lambda: oe.updates(timeout=window_s)),
                     daemon=True).start()
    while not stop.is_set():
        try:
            yield q.get(timeout=timer_s)
        except queue.Empty:
            yield ("timer", None)


def run_strategy_live(client: Any, strategy: Strategy | str, *,
                      symbols: list[str], params: dict[str, Any] | None = None,
                      account: str = "", strategy_tag: str = "strat",
                      timer_s: float = 1.0,
                      stop: threading.Event | None = None) -> None:
    """Run a strategy against a live/paper credential (rung 3).

    `strategy` may be a Strategy instance or a path to a .py file. Opens market
    data + order entry, subscribes `symbols`, and dispatches until `stop` is set
    (wire it to SIGINT in the CLI). Orders are tagged with `strategy_tag`.
    """
    if isinstance(strategy, str):
        strategy = load_strategy(strategy)
    stop = stop or threading.Event()
    with client.market_data() as md, client.orders() as oe:
        md.subscribe(symbols)
        ctx = LiveContext(oe, strategy_tag=strategy_tag, account=account)
        ctx.params = params or {}
        Supervisor(strategy, ctx).run(merge_streams(md, oe, timer_s=timer_s, stop=stop))
