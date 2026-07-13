"""Auto-tools — hardened, parameterized strategies (plan §10.2).

The WinForms AutoTool family (Legger, Scalper, RangerF) is 15 years of evidence
that most traders **parameterize a hardened automation through a form** and only
sometimes write code. Auto-tools are that: shipped `Strategy` subclasses configured
by params, no user code — which also makes them trivially hostable (no arbitrary
code to sandbox), quietly solving the hosted-runner problem for most users.

The LLM bridges the spectrum (§10.2): its output can be a *parameter set* for one
of these ("this idea is a scalper with edge=0.05, target=0.10") or new code when
no template fits. Every auto-tool runs unmodified in backtest / paper / live.
"""
from __future__ import annotations

from .strategy import Strategy

# name -> Strategy subclass (used by the CLI/MCP to run an auto-tool by name)
REGISTRY: dict[str, type] = {}


def _register(name: str):
    def deco(cls):
        REGISTRY[name] = cls
        return cls
    return deco


@_register("scalper")
class Scalper(Strategy):
    """Rest a bid below the market; on a fill, rest an exit above cost for a small
    profit; scale in up to ``max_position``. Params (all optional):

        symbol        restrict to one symbol (else trades every symbol it sees)
        size          lots per entry            (default 1)
        edge          rest the entry this far below the close   (default 0.05)
        target        take profit this far above the fill/close (default 0.05)
        max_position  max net long lots          (default 3)
    """

    def on_start(self, ctx):
        self.symbol = ctx.param("symbol")
        self.size = int(ctx.param("size", 1))
        self.edge = float(ctx.param("edge", 0.05))
        self.target = float(ctx.param("target", 0.05))
        self.max_position = int(ctx.param("max_position", 3))
        self.entry_cid: str | None = None
        self.exit_cid: str | None = None

    def _mine(self, sym: str) -> bool:
        return self.symbol is None or sym == self.symbol

    def on_bar(self, ctx, bar):
        sym = bar["symbol"]
        close = bar.get("close")
        if not self._mine(sym) or close is None:
            return
        pos = ctx.position(sym)
        # entry: rest a bid below the market while we have room to add
        if pos < self.max_position and not self.entry_cid:
            self.entry_cid = ctx.buy(sym, self.size, round(close - self.edge, 4))
        # exit: while long, keep a fresh take-profit sell for the whole position
        if pos > 0:
            if self.exit_cid:
                ctx.cancel(self.exit_cid)
            self.exit_cid = ctx.sell(sym, pos, round(close + self.target, 4))
        elif self.exit_cid:
            ctx.cancel(self.exit_cid)
            self.exit_cid = None

    def on_fill(self, ctx, fill):
        cid = fill.get("cid")
        if cid == self.entry_cid:
            self.entry_cid = None      # free the entry slot to scale in again
        if cid == self.exit_cid:
            self.exit_cid = None


def make_auto_tool(name: str) -> Strategy:
    """Instantiate a registered auto-tool by name (raises KeyError if unknown)."""
    return REGISTRY[name]()
