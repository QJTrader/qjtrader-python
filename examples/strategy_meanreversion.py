"""A tiny mean-reversion strategy — the same file runs in backtest and live.

    qjtrader backtest examples/strategy_meanreversion.py --symbol MX:CRAU26 --bars 200
    qjtrader run       examples/strategy_meanreversion.py --symbols MX:CRAU26 --tag mr1

It keeps a rolling average of closes and buys 1 lot when price dips a threshold
below the average (flat-only), exiting when price reverts above it. Illustrative,
not advice.
"""
from collections import deque

from qjtrader import Strategy


class MeanReversion(Strategy):
    def on_start(self, ctx):
        self.window = deque(maxlen=int(ctx.param("window", 20)))
        self.dip = float(ctx.param("dip", 0.02))     # buy this far below the average
        self.sym = ctx.param("symbol", None)

    def on_bar(self, ctx, bar):
        sym = bar["symbol"]
        close = bar.get("close")
        if close is None:
            return
        self.window.append(close)
        if len(self.window) < self.window.maxlen:
            return
        avg = sum(self.window) / len(self.window)
        pos = ctx.position(sym)
        if pos == 0 and close <= avg - self.dip:
            ctx.buy(sym, 1, close, tif="ioc")        # enter long at the market
        elif pos > 0 and close >= avg:
            ctx.sell(sym, pos, close, tif="ioc")     # revert -> exit
