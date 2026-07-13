"""Book-native (L2) backtest — run-venue rung 1, microstructure fidelity (plan §10.3
+ §8). Where `backtest.py` fills at bar level (good enough for *logic*), this replays
the **actual L2 book + tape** and fills through the **same queue-position model the
paper environment uses**, so a strategy's fills here match how it would fill live —
the "truth" moat expressed in the research loop.

Same `Strategy` contract as every other venue, so one file runs in bar-backtest,
L2-backtest, paper, and live. Deterministic and offline: feed it recorded L2 events
(the capture tee's raw ticks) or `synthetic_l2_events(...)`.

Fill model (identical in spirit to `qj_orders.paper_matcher`, v1):
  - **marketable** orders walk displayed liquidity, price-improving (`fok` all-or-none;
    `ioc` fills what it can then cancels; `day` rests the remainder);
  - **passive** orders rest and fill **only on trade-through**, after the displayed
    size ahead of them in the queue (captured at rest) has traded.
"""
from __future__ import annotations

import random
from typing import Any, Iterable

from .backtest import BacktestReport
from .strategy import Context, PositionBook, Strategy

FILL_MODEL = "queue-v1"


class _QueueMatcher:
    """Synchronous mirror of the PaperMatcher honest-fill model."""

    def __init__(self, ctx: "L2Context") -> None:
        self.ctx = ctx
        self.resting: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _marketable(side: str, price: float, levels: list[dict]) -> bool:
        if not levels or price is None:
            return False
        best = levels[0].get("price")
        return best is not None and (price >= best if side == "buy" else price <= best)

    def place(self, order: dict[str, Any]) -> None:
        side, qty, price, tif = order["side"], order["qty"], order["price"], order["tif"]
        book = self.ctx.books.get(order["sym"]) or {"bids": [], "asks": []}
        levels = book.get("asks" if side == "buy" else "bids") or []
        cum = 0
        if self._marketable(side, price, levels):
            acceptable = [lv for lv in levels if lv.get("price") is not None
                          and (lv["price"] <= price if side == "buy" else lv["price"] >= price)]
            available = sum(int(lv.get("size") or 0) for lv in acceptable)
            if tif == "fok" and available < qty:
                order["status"] = "canceled"
                return
            for lv in acceptable:
                if cum >= qty:
                    break
                take = min(qty - cum, int(lv.get("size") or 0))
                if take <= 0:
                    continue
                cum += take
                self.ctx._fill(order, take, lv["price"])
            if cum >= qty:
                return
            if tif in ("ioc", "fok"):
                order["status"] = "canceled"
                return
        elif tif in ("ioc", "fok"):
            order["status"] = "canceled"
            return
        # rest the remainder passively
        order["cum"] = cum
        order["queue_ahead"] = self._displayed_at(side, price, book)
        self.resting[order["cid"]] = order

    @staticmethod
    def _displayed_at(side: str, price: float, book: dict) -> int:
        levels = book.get("bids" if side == "buy" else "asks") or []
        return sum(int(lv.get("size") or 0) for lv in levels if lv.get("price") == price)

    def on_trade(self, sym: str, price: float, size: int) -> None:
        for cid, r in list(self.resting.items()):
            if r["sym"] != sym or r["price"] is None:
                continue
            hits = (price <= r["price"]) if r["side"] == "buy" else (price >= r["price"])
            if not hits:
                continue
            consumed = size
            if r["queue_ahead"] > 0:
                eat = min(r["queue_ahead"], consumed)
                r["queue_ahead"] -= eat
                consumed -= eat
            if consumed <= 0:
                continue
            fill = min(r["qty"] - r["cum"], consumed)
            if fill <= 0:
                continue
            r["cum"] += fill
            self.ctx._fill(r, fill, r["price"])
            if r["cum"] >= r["qty"]:
                r["status"] = "filled"
                self.resting.pop(cid, None)

    def cancel(self, cid: str) -> None:
        o = self.resting.pop(cid, None)
        if o:
            o["status"] = "canceled"


class L2Context(Context):
    def __init__(self, params: dict[str, Any], strategy: Strategy, tag: str = "l2") -> None:
        self.params = params
        self.strategy = strategy
        self.tag = tag
        self._seq = 0
        self._clock = 0.0
        self.books: dict[str, dict[str, Any]] = {}
        self.marks: dict[str, float] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.fills: list[dict[str, Any]] = []
        self.logs: list[str] = []
        self.pos: dict[str, PositionBook] = {}
        self.matcher = _QueueMatcher(self)

    # Context API
    def param(self, key, default=None):
        return self.params.get(key, default)

    def now(self):
        return self._clock

    def log(self, *args):
        self.logs.append(" ".join(str(a) for a in args))

    def _cid(self, cid):
        if cid:
            return cid
        self._seq += 1
        return f"{self.tag}-{self._seq}"

    def _place(self, sym, side, qty, price, tif, cid):
        cid = self._cid(cid)
        order = {"cid": cid, "sym": sym, "side": side, "qty": qty, "price": price,
                 "tif": tif, "status": "open", "cum": 0}
        self.orders[cid] = order
        self.matcher.place(order)
        return cid

    def buy(self, sym, qty, price, *, tif="day", account="", cid=None):
        return self._place(sym, "buy", qty, price, tif, cid)

    def sell(self, sym, qty, price, *, tif="day", account="", cid=None):
        return self._place(sym, "sell", qty, price, tif, cid)

    def cancel(self, cid):
        self.matcher.cancel(cid)

    def replace(self, cid, *, qty=None, price=None):
        self.matcher.cancel(cid)  # simplest honest model: cancel + (strategy re-places)

    def position(self, sym):
        return self.pos[sym].net if sym in self.pos else 0

    def positions(self):
        return {s: b.net for s, b in self.pos.items() if b.net}

    def quote(self, sym):
        b = self.books.get(sym)
        if not b:
            return None
        bid = b["bids"][0]["price"] if b.get("bids") else None
        ask = b["asks"][0]["price"] if b.get("asks") else None
        return {"bid": bid, "ask": ask, "last": self.marks.get(sym)}

    def _fill(self, order, qty, price):
        self.pos.setdefault(order["sym"], PositionBook()).apply(order["side"], qty, price)
        fill = {"type": "exec", "cid": order["cid"], "sym": order["sym"],
                "side": order["side"], "qty": qty, "price": price, "status": "filled",
                "fill_model": FILL_MODEL, "ts": self._clock}
        self.fills.append(fill)
        self.strategy.on_fill(self, fill)


def run_l2_backtest(strategy: Strategy, events: Iterable[dict[str, Any]], *,
                    params: dict[str, Any] | None = None,
                    strategy_tag: str = "l2") -> BacktestReport:
    """Replay L2 book + trade events through `strategy` with queue-honest fills."""
    ctx = L2Context(params or {}, strategy, strategy_tag)
    strategy.on_start(ctx)
    n = 0
    for ev in events:
        n += 1
        sym = ev.get("symbol")
        data = ev.get("data") or {}
        ctx._clock = ev.get("ts", ctx._clock)
        etype = ev.get("type")
        if etype in ("level2", "snapshot"):
            ctx.books[sym] = {"bids": data.get("bids") or [], "asks": data.get("asks") or []}
            strategy.on_depth(ctx, ev)
            q = ctx.quote(sym)
            if q:
                strategy.on_quote(ctx, {"type": "quote", "symbol": sym,
                                        "data": {"bid": q["bid"], "ask": q["ask"]}})
        elif etype == "trade":
            price = data.get("price")
            size = int(data.get("size") or 0)
            if price is not None:
                ctx.marks[sym] = price
                ctx.matcher.on_trade(sym, price, size)  # passive trade-through fills
                strategy.on_trade(ctx, ev)
    strategy.on_stop(ctx)
    realized = sum(b.realized for b in ctx.pos.values())
    unreal = sum(b.unrealized(ctx.marks.get(s)) for s, b in ctx.pos.items())
    return BacktestReport({
        "events": n,
        "orders": len(ctx.orders),
        "fills": ctx.fills,
        "positions": ctx.positions(),
        "realized_pnl": round(realized, 6),
        "unrealized_pnl": round(unreal, 6),
        "total_pnl": round(realized + unreal, 6),
        "fill_model": FILL_MODEL,
        "logs": ctx.logs,
    })


def synthetic_l2_events(symbol: str, count: int, *, seed: int | None = None,
                        depth: int = 5, start: float = 0.0) -> list[dict[str, Any]]:
    """Deterministic offline L2 stream: a random-walking book with occasional prints.
    Emits `level2` snapshots interleaved with `trade` events."""
    rng = random.Random(seed if seed is not None else (sum(ord(c) for c in symbol) or 1))
    is_mx = symbol.upper().startswith("MX:")
    mid = round(90.0 + (sum(ord(c) for c in symbol) % 900) / 100.0, 3) if is_mx \
        else round(20.0 + (sum(ord(c) for c in symbol) % 18000) / 100.0, 2)
    tick, dp = (0.005, 3) if is_mx else (0.01, 2)
    out: list[dict[str, Any]] = []
    t = start
    for _ in range(count):
        mid = max(tick * 10, round(mid + rng.choice((-1, 0, 1)) * tick, dp))
        bids = [{"price": round(mid - (i + 1) * tick, dp), "size": rng.randint(1, 20) * 10}
                for i in range(depth)]
        asks = [{"price": round(mid + (i + 1) * tick, dp), "size": rng.randint(1, 20) * 10}
                for i in range(depth)]
        out.append({"type": "level2", "symbol": symbol, "ts": t,
                    "data": {"bids": bids, "asks": asks}})
        if rng.random() < 0.5:
            px = round(mid + rng.choice((-tick, 0.0, tick)), dp)
            out.append({"type": "trade", "symbol": symbol, "ts": t + 0.1,
                        "data": {"price": px, "size": rng.randint(1, 10) * 10}})
        t += 1.0
    return out
