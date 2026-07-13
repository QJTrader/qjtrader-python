"""Backtest engine — run-venue rung 1 (plan §10.3): the strategy contract driven
over historical/synthetic bars, in-process, **no network and no secrets** (so it
is trivially sandboxable). Same strategy file as paper/live.

Fill model (v1, bar-level, honest about its limits): a resting limit order fills
when a later bar trades through its price (buy: bar low <= price; sell: bar high
>= price) at the limit price; ``ioc``/``fok`` orders fill immediately if
marketable versus the current bar's close, else cancel. Queue-position and L2
fidelity come from the **paper** environment (§8), not here — a backtest is for
logic, the paper run is for microstructure truth.
"""
from __future__ import annotations

import random
from typing import Any, Iterable

from .strategy import Context, PositionBook, Strategy

_TIF = ("day", "ioc", "fok")


def synthetic_bars(symbol: str, count: int, *, interval_s: int = 60,
                   seed: int | None = None, start: float = 0.0) -> list[dict[str, Any]]:
    """Deterministic, reproducible offline bars for a symbol (no network).

    Same seed => identical series, so a strategy can be re-run against the exact
    same market after a code change (§7.6). Mirrors the feed's synthetic shape.
    """
    rng = random.Random(seed if seed is not None else (sum(ord(c) for c in symbol) or 1))
    is_mx = symbol.upper().startswith("MX:")
    mid = round(90.0 + (sum(ord(c) for c in symbol) % 900) / 100.0, 3) if is_mx \
        else round(20.0 + (sum(ord(c) for c in symbol) % 18000) / 100.0, 2)
    tick, dp = (0.005, 3) if is_mx else (0.01, 2)
    out = []
    t = start
    for _ in range(count):
        o = mid
        hi = lo = c = o
        for _ in range(rng.randint(1, 6)):
            mid = max(tick * 10, round(mid + rng.choice((-1, 0, 1)) * tick, dp))
            hi, lo, c = max(hi, mid), min(lo, mid), mid
        spread = round(tick * rng.choice((1, 1, 2)), dp)
        out.append({"symbol": symbol, "start": t, "open": round(o, dp),
                    "high": round(hi, dp), "low": round(lo, dp), "close": round(c, dp),
                    "volume": rng.randint(0, 20) * 10,
                    "bid": round(c - spread / 2, dp), "ask": round(c + spread / 2, dp),
                    "spread": spread})
        t += interval_s
    return out


class BacktestContext(Context):
    def __init__(self, params: dict[str, Any], strategy_tag: str = "bt") -> None:
        self.params = params
        self.tag = strategy_tag
        self._seq = 0
        self._clock = 0.0
        self.orders: dict[str, dict[str, Any]] = {}
        self.open: set[str] = set()
        self.fills: list[dict[str, Any]] = []
        self.logs: list[str] = []
        self.books: dict[str, PositionBook] = {}
        self.marks: dict[str, float] = {}
        self._bar: dict[str, Any] | None = None
        self._on_fill = None  # set by run_backtest so matched fills reach the strategy

    # --- Context API --------------------------------------------------------
    def param(self, key, default=None):
        return self.params.get(key, default)

    def now(self):
        return self._clock

    def log(self, *args):
        self.logs.append(" ".join(str(a) for a in args))

    def _book(self, sym):
        return self.books.setdefault(sym, PositionBook())

    def _cid(self, cid):
        if cid:
            return cid
        self._seq += 1
        return f"{self.tag}-{self._seq}"

    def _place(self, sym, side, qty, price, tif, cid):
        cid = self._cid(cid)
        order = {"cid": cid, "sym": sym, "side": side, "qty": qty, "price": price,
                 "tif": tif, "status": "open", "filled": 0}
        self.orders[cid] = order
        if tif in ("ioc", "fok") and self._bar is not None:
            close = self._bar.get("close")
            marketable = close is not None and (
                (side == "buy" and price >= close) or (side == "sell" and price <= close))
            if marketable:
                self._fill(order, close)
            else:
                order["status"] = "canceled"
            return cid
        self.open.add(cid)
        return cid

    def buy(self, sym, qty, price, *, tif="day", account="", cid=None):
        return self._place(sym, "buy", qty, price, tif, cid)

    def sell(self, sym, qty, price, *, tif="day", account="", cid=None):
        return self._place(sym, "sell", qty, price, tif, cid)

    def cancel(self, cid):
        o = self.orders.get(cid)
        if o and o["status"] == "open":
            o["status"] = "canceled"
            self.open.discard(cid)

    def replace(self, cid, *, qty=None, price=None):
        o = self.orders.get(cid)
        if o and o["status"] == "open":
            if qty is not None:
                o["qty"] = qty
            if price is not None:
                o["price"] = price

    def position(self, sym):
        return self._book(sym).net

    def positions(self):
        return {s: b.net for s, b in self.books.items() if b.net}

    def quote(self, sym):
        b = self._bar if self._bar and self._bar.get("symbol") == sym else None
        if b is None:
            return None
        return {"bid": b.get("bid"), "ask": b.get("ask"), "last": b.get("close")}

    # --- matching -----------------------------------------------------------
    def _fill(self, order, price):
        order["status"] = "filled"
        order["filled"] = order["qty"]
        self.open.discard(order["cid"])
        self._book(order["sym"]).apply(order["side"], order["qty"], price)
        fill = {"type": "exec", "cid": order["cid"], "sym": order["sym"],
                "side": order["side"], "qty": order["qty"], "price": price,
                "status": "filled", "ts": self._clock}
        self.fills.append(fill)
        if self._on_fill is not None:
            self._on_fill(fill)

    def _match(self, bar):
        sym = bar.get("symbol")
        lo, hi = bar.get("low"), bar.get("high")
        for cid in list(self.open):
            o = self.orders[cid]
            if o["sym"] != sym:
                continue
            if o["side"] == "buy" and lo is not None and lo <= o["price"]:
                self._fill(o, o["price"])
            elif o["side"] == "sell" and hi is not None and hi >= o["price"]:
                self._fill(o, o["price"])


class BacktestReport(dict):
    """A plain dict (JSON-friendly) with the run's outcome."""


def run_backtest(strategy: Strategy, bars: Iterable[dict[str, Any]], *,
                 params: dict[str, Any] | None = None,
                 strategy_tag: str = "bt") -> BacktestReport:
    """Drive `strategy` over `bars` and return a report (fills, positions, PnL).

    Each bar: match resting orders from prior bars (no lookahead), then dispatch
    on_quote/on_trade (synthesized from the bar), on_bar and on_timer.
    """
    ctx = BacktestContext(params or {}, strategy_tag)
    ctx._on_fill = lambda f: strategy.on_fill(ctx, f)
    strategy.on_start(ctx)
    equity_curve: list[dict[str, Any]] = []
    n = 0
    for bar in bars:
        n += 1
        sym = bar.get("symbol")
        ctx._clock = bar.get("start", ctx._clock)
        ctx._bar = bar
        if bar.get("close") is not None:
            ctx.marks[sym] = bar["close"]
        ctx._match(bar)  # fills from earlier orders arrive first
        strategy.on_quote(ctx, {"type": "quote", "symbol": sym,
                                "data": {"bid": bar.get("bid"), "ask": bar.get("ask")}})
        if bar.get("close") is not None:
            strategy.on_trade(ctx, {"type": "trade", "symbol": sym,
                                    "data": {"price": bar["close"],
                                             "size": bar.get("volume", 0)}})
        strategy.on_bar(ctx, bar)
        strategy.on_timer(ctx)
        realized = sum(b.realized for b in ctx.books.values())
        unreal = sum(b.unrealized(ctx.marks.get(s)) for s, b in ctx.books.items())
        equity_curve.append({"t": ctx._clock, "pnl": round(realized + unreal, 6)})
    strategy.on_stop(ctx)
    realized = sum(b.realized for b in ctx.books.values())
    unreal = sum(b.unrealized(ctx.marks.get(s)) for s, b in ctx.books.items())
    return BacktestReport({
        "bars": n,
        "orders": len(ctx.orders),
        "fills": ctx.fills,
        "positions": ctx.positions(),
        "realized_pnl": round(realized, 6),
        "unrealized_pnl": round(unreal, 6),
        "total_pnl": round(realized + unreal, 6),
        "equity_curve": equity_curve,
        "logs": ctx.logs,
    })
