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

import hashlib
import importlib.util
import inspect
import json
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


def strategy_version(strategy: Strategy, params: dict[str, Any] | None) -> str:
    """A short, stable content hash of the exact strategy code + params (plan §10.5
    v5). Folded into the order tag so every journaled order is attributable to the
    precise agent *version* that produced it — and a promotion is granted to a
    version, not a name. Changing the code or the params changes the hash."""
    try:
        src = inspect.getsource(type(strategy))
    except (OSError, TypeError):  # e.g. defined in a REPL — fall back to the name
        src = type(strategy).__name__
    blob = src + "\n" + json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]


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


# --------------------------------------------------------------- bar synthesis
class _BarBuilder:
    """Folds live quotes/trades into fixed-interval OHLCV bars so bar-driven
    strategies (the shipped auto-tools, the examples) run **unmodified** on the
    live/paper path — not just in the backtester. Without this the strategy
    contract's "same file everywhere" promise (§10.1) breaks live: the supervisor
    only sees ticks. Close = last trade price, or the quote mid when a bar had no
    prints (so a bar still forms in quiet names). Volume = summed trade size.
    """

    def __init__(self, interval_s: float, clock=time.time) -> None:
        self.interval = interval_s
        self._clock = clock
        self._cur: dict[str, dict[str, Any]] = {}
        self._mid: dict[str, float] = {}

    @staticmethod
    def _bucket(ts: float, iv: float) -> float:
        return (ts // iv) * iv

    def _bar(self, sym: str, now: float) -> dict[str, Any]:
        b = self._cur.get(sym)
        bucket = self._bucket(now, self.interval)
        if b is None or b["_bucket"] != bucket:
            b = {"symbol": sym, "_bucket": bucket, "open": None, "high": None,
                 "low": None, "close": None, "volume": 0.0}
            self._cur[sym] = b
        return b

    def on_trade(self, sym: str, px: float, sz: float, now: float) -> None:
        b = self._bar(sym, now)
        if b["open"] is None:
            b["open"] = b["high"] = b["low"] = px
        b["high"] = max(b["high"], px)
        b["low"] = min(b["low"], px)
        b["close"] = px
        b["volume"] += sz

    def on_quote(self, sym: str, bid, ask, now: float) -> None:
        if bid is not None and ask is not None:
            self._mid[sym] = (float(bid) + float(ask)) / 2.0
            self._bar(sym, now)   # ensure a bucket exists so quote-only names form bars too

    def roll(self, now: float) -> list[dict[str, Any]]:
        """Finalize and return any bars whose interval has fully elapsed."""
        out: list[dict[str, Any]] = []
        for sym, b in list(self._cur.items()):
            if b["_bucket"] + self.interval > now:
                continue
            if b["close"] is None:                 # no trades this bar — use quote mid
                mid = self._mid.get(sym)
                if mid is None:
                    del self._cur[sym]
                    continue
                b["open"] = b["high"] = b["low"] = b["close"] = mid
            out.append({k: v for k, v in b.items() if not k.startswith("_")})
            del self._cur[sym]
        return out


# ------------------------------------------------------------------ supervisor
class Supervisor:
    """Dispatches merged (kind, msg) events to a strategy. Transport-agnostic.

    When ``bar_interval`` > 0 it also synthesizes OHLCV bars from the live tick
    stream and calls ``on_bar`` at each boundary (checked on timer ticks), so
    bar-driven strategies work on the live/paper path exactly as in the backtest.
    """

    def __init__(self, strategy: Strategy, ctx: LiveContext,
                 bar_interval: float = 0.0, clock=time.time) -> None:
        self.strategy = strategy
        self.ctx = ctx
        self._bars = _BarBuilder(bar_interval, clock) if bar_interval > 0 else None
        self._clock = clock

    def start(self) -> None:
        self.strategy.on_start(self.ctx)

    def _roll_bars(self) -> None:
        # Roll on EVERY dispatch, not just timer ticks: a busy symbol keeps the
        # merge queue non-empty so timer ticks are starved, and bar-driven
        # strategies would never fire under load if we waited for a quiet second.
        if self._bars is not None:
            for bar in self._bars.roll(self._clock()):
                self.strategy.on_bar(self.ctx, bar)

    def dispatch(self, kind: str, msg: dict[str, Any] | None) -> None:
        self._roll_bars()
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
                    if self._bars is not None:
                        self._bars.on_quote(sym, data.get("bid"), data.get("ask"),
                                            self._clock())
                self.strategy.on_quote(self.ctx, msg)
            elif mtype in ("level2", "snapshot"):
                self.strategy.on_depth(self.ctx, msg)
            elif mtype == "trade":
                px = (msg.get("data") or {}).get("price")
                if sym and px is not None:
                    self.ctx.marks[sym] = px
                    if self._bars is not None:
                        self._bars.on_trade(sym, float(px),
                                            float((msg.get("data") or {}).get("size") or 0),
                                            self._clock())
                self.strategy.on_trade(self.ctx, msg)
        elif kind == "oe":
            # on_fill fires ONLY for actual fills — same contract as the backtest
            # engine. Accepted/new/rejected updates are journaled server-side (the
            # blotter shows them) but must NOT reach on_fill, or a strategy that
            # frees an order slot on its cid (e.g. the scalper) would do so on the
            # order's own 'accepted' echo and re-fire every bar.
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
    dead = threading.Event()  # a source stream closed/errored — end the merge so the
    #                           caller can reconnect (a dropped gateway must not leave
    #                           the run spinning forever on timer ticks with no data).

    def pump(kind: str, src_factory) -> None:
        try:
            while not stop.is_set():
                for msg in src_factory():
                    q.put((kind, msg))
                    if stop.is_set():
                        return
        except Exception:
            pass
        finally:
            dead.set()

    threading.Thread(target=pump, args=("md", lambda: md.messages(timeout=window_s)),
                     daemon=True).start()
    threading.Thread(target=pump, args=("oe", lambda: oe.updates(timeout=window_s)),
                     daemon=True).start()
    while not stop.is_set() and not dead.is_set():
        try:
            yield q.get(timeout=timer_s)
        except queue.Empty:
            yield ("timer", None)


def run_strategy_live(client: Any, strategy: Strategy | str, *,
                      symbols: list[str], params: dict[str, Any] | None = None,
                      account: str = "", strategy_tag: str = "strat",
                      timer_s: float = 1.0,
                      stop: threading.Event | None = None,
                      reconnect: bool = True,
                      reconnect_backoff_s: float = 3.0) -> None:
    """Run a strategy against a live/paper credential (rung 3).

    `strategy` may be a Strategy instance or a path to a .py file. Opens market
    data + order entry, subscribes `symbols`, and dispatches until `stop` is set
    (wire it to SIGINT in the CLI). Orders are tagged with `strategy_tag`.

    With `reconnect` (default), a dropped connection (e.g. a gateway restart) is not
    fatal: the run backs off and re-opens the streams, re-running `on_start`, until
    `stop` is set — so a hosted 24/7 run self-heals rather than dying. Set
    `reconnect=False` for one-shot semantics (the old behaviour).
    """
    if isinstance(strategy, str):
        strategy = load_strategy(strategy)
    stop = stop or threading.Event()
    params = params or {}
    # Fold the immutable strategy-version hash into the tag (§10.5 v5): orders are
    # cid'd `<tag>.<ver>-<seq>`, so the gateway's per-tag position/envelope/journal
    # all scope to the exact version — promotion is granted to a version, not a name.
    version = strategy_version(strategy, params)
    versioned_tag = f"{strategy_tag}.{version}"
    # Synthesize bars from the live tick stream so bar-driven strategies run here
    # exactly as in the backtest (§10.1). `bar_interval_s` param overrides; 0 = off.
    bar_interval = float(params.get("bar_interval_s", 5.0))
    while not stop.is_set():
        try:
            with client.market_data() as md, client.orders() as oe:
                md.subscribe(symbols)
                ctx = LiveContext(oe, strategy_tag=versioned_tag, account=account)
                ctx.params = params
                # merge_streams returns when stop is set (clean) or a stream drops.
                Supervisor(strategy, ctx, bar_interval=bar_interval).run(
                    merge_streams(md, oe, timer_s=timer_s, stop=stop))
        except Exception:
            if not reconnect or stop.is_set():
                raise
        if not reconnect or stop.is_set():
            break
        stop.wait(reconnect_backoff_s)  # transient drop — back off, then reconnect
