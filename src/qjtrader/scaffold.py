"""The one small, safe local strategy project scaffold."""
from __future__ import annotations

from pathlib import Path

STRATEGY = '''from qjtrader import Strategy


class FirstStrategy(Strategy):
    """A deliberately small learning strategy.

    It observes by default. Orders require allow_orders=true, so the same file
    cannot begin trading merely because credentials were added later.
    """

    def on_bar(self, ctx, bar):
        symbol = bar["symbol"]
        ctx.log(symbol, "close", bar["close"])
        if not ctx.param("allow_orders", False) or ctx.position(symbol) != 0:
            return
        edge = float(ctx.param("buy_below", bar["close"] * 1.001))
        if bar["close"] < edge:
            ctx.buy(symbol, 1, bar["close"], tif="ioc", account=ctx.param("account", "SIM"))
'''

TEST_STRATEGY = '''import unittest

from qjtrader import run_backtest, synthetic_bars
from strategy import FirstStrategy


class FirstStrategyTest(unittest.TestCase):
    def test_observation_mode_places_no_orders(self):
        report = run_backtest(
            FirstStrategy(),
            synthetic_bars("{symbol}", 20, seed=7),
            params={{"allow_orders": False}},
        )
        self.assertEqual(report["orders"], 0)


if __name__ == "__main__":
    unittest.main()
'''

README = '''# My first QJ strategy

This project starts in observation mode. Test it with reproducible synthetic bars:

```powershell
qjtrader backtest strategy.py --symbol {symbol}
```

To exercise its one-unit order logic in a backtest:

```powershell
qjtrader backtest strategy.py --symbol {symbol} --param allow_orders=true
```

Before a connected run, confirm the credential environment. Use a sandbox key first:

```powershell
qjtrader run strategy.py --symbols {symbol} --tag first --run-id first --account SIM --param allow_orders=true
```

The run appears on the Gateway Wire with its versioned identity. Inspect or stop it from another
terminal (or ask your coding agent to do this):

```powershell
qjtrader runs
qjtrader stop-run first
```

Ctrl-C also stops it. Either path calls the strategy stop hook and cancels its working orders.
'''


def create_strategy_project(path: str, *, symbol: str = "CA:RY", force: bool = False) -> list[str]:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        root / "strategy.py": STRATEGY,
        root / "test_strategy.py": TEST_STRATEGY.format(symbol=symbol),
        root / "README.md": README.format(symbol=symbol),
    }
    existing = [str(p) for p in files if p.exists()]
    if existing and not force:
        raise FileExistsError(f"refusing to overwrite: {', '.join(existing)}")
    for file, content in files.items():
        file.write_text(content, encoding="utf-8")
    return [str(p) for p in files]
