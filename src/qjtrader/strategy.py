"""The strategy contract — the load-bearing design decision (plan §10.1).

"Where does the user's strategy run?" is an API question wearing an infrastructure
costume. Define one small contract and **the same file runs unmodified in every
venue**: backtest, paper, local live, hosted.

    class MyStrategy(Strategy):
        def on_start(self, ctx):
            ctx.log("hello")
        def on_bar(self, ctx, bar):          # backtest / analytics granularity
            if bar["close"] < ctx.param("buy_below", 0):
                ctx.buy(bar["symbol"], 1, bar["close"])
        def on_quote(self, ctx, quote): ...   # live tick granularity
        def on_fill(self, ctx, fill): ...

The supervisor owns the client, heartbeat and the ``strategy`` tag on every order
(so every order is automatically journal-grouped and observable). The LLM authors
against this contract; deterministic code executes it; the workbench observes.

Multi-asset from day one (plan §10.1): ``ctx`` exposes positions and order entry
for equities (venue-aware symbols like ``CA:RY.PT``), futures (with ``on_roll``),
and options; greeks/chain access hang off ``ctx`` where the data supports them.
"""
from __future__ import annotations

from typing import Any, Protocol


# --------------------------------------------------------------- position math
class PositionBook:
    """Average-cost net position + realized PnL for one symbol."""

    __slots__ = ("net", "avg", "realized")

    def __init__(self) -> None:
        self.net = 0            # signed quantity (+long / -short)
        self.avg = 0.0          # average cost of the open position
        self.realized = 0.0

    def apply(self, side: str, qty: int, price: float) -> None:
        signed = qty if side == "buy" else -qty
        old = self.net
        if old == 0 or (old > 0) == (signed > 0):     # opening / increasing
            total = self.avg * abs(old) + price * abs(signed)
            self.net = old + signed
            self.avg = total / abs(self.net) if self.net else 0.0
            return
        # reducing / closing (opposite sign)
        closing = min(abs(old), abs(signed))
        self.realized += (price - self.avg) * closing * (1 if old > 0 else -1)
        self.net = old + signed
        if self.net == 0:
            self.avg = 0.0
        elif abs(signed) > abs(old):                  # flipped through zero
            self.avg = price
        # else: partial reduction — avg (of the remaining position) is unchanged

    def unrealized(self, mark: float | None) -> float:
        if mark is None or self.net == 0:
            return 0.0
        return (mark - self.avg) * self.net


# ------------------------------------------------------------------- context
class Context(Protocol):
    """What a strategy is handed. Implemented by the backtest and live harnesses,
    so a strategy calls the same methods regardless of where it runs."""

    def param(self, key: str, default: Any = None) -> Any: ...
    def now(self) -> float: ...
    def log(self, *args: Any) -> None: ...
    def buy(self, sym: str, qty: int, price: float, *, tif: str = "day",
            account: str = "", cid: str | None = None) -> str: ...
    def sell(self, sym: str, qty: int, price: float, *, tif: str = "day",
             account: str = "", cid: str | None = None) -> str: ...
    def cancel(self, cid: str) -> None: ...
    def replace(self, cid: str, *, qty: int | None = None,
                price: float | None = None) -> None: ...
    def position(self, sym: str) -> int: ...
    def positions(self) -> dict[str, int]: ...
    def quote(self, sym: str) -> dict[str, Any] | None: ...


# ------------------------------------------------------------------ strategy
class Strategy:
    """Base class: subclass and override the callbacks you need. All are no-ops
    by default, so a strategy only implements what it cares about.

    Granularity: ``on_bar`` is the backtest/analytics entry (fires in backtest,
    and live once bar aggregation is on); ``on_quote``/``on_trade``/``on_depth``
    are the live tick entries. A portable strategy can use either.
    """

    def on_start(self, ctx: Context) -> None: ...
    def on_bar(self, ctx: Context, bar: dict[str, Any]) -> None: ...
    def on_quote(self, ctx: Context, quote: dict[str, Any]) -> None: ...
    def on_depth(self, ctx: Context, depth: dict[str, Any]) -> None: ...
    def on_trade(self, ctx: Context, trade: dict[str, Any]) -> None: ...
    def on_fill(self, ctx: Context, fill: dict[str, Any]) -> None: ...
    def on_timer(self, ctx: Context) -> None: ...
    def on_roll(self, ctx: Context, old: str, new: str) -> None: ...
    def on_stop(self, ctx: Context) -> None: ...
