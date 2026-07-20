"""Strategy contract, backtest engine, and live supervisor (plan §10)."""
import json

import pytest

from qjtrader import (LiveContext, Strategy, Supervisor, load_strategy,
                      run_backtest, synthetic_bars)
from qjtrader.strategy import PositionBook


# ------------------------------------------------------------- position math
def test_position_book_long_close_and_realized():
    b = PositionBook()
    b.apply("buy", 10, 100.0)
    assert b.net == 10 and b.avg == 100.0
    b.apply("buy", 10, 102.0)               # average up
    assert b.net == 20 and b.avg == 101.0
    b.apply("sell", 5, 106.0)               # close 5 @ +5
    assert b.net == 15 and round(b.realized, 6) == 25.0
    assert round(b.unrealized(111.0), 6) == round((111.0 - 101.0) * 15, 6)


def test_position_book_flip_through_zero():
    b = PositionBook()
    b.apply("buy", 5, 100.0)
    b.apply("sell", 8, 110.0)               # close 5 @ +50, then short 3 @ 110
    assert b.net == -3 and b.avg == 110.0
    assert round(b.realized, 6) == 50.0


# ------------------------------------------------------------------ synthetic
def test_synthetic_bars_deterministic():
    a = synthetic_bars("MX:CRAU26", 100, seed=7)
    b = synthetic_bars("MX:CRAU26", 100, seed=7)
    assert a == b and len(a) == 100
    assert all(x["low"] <= x["close"] <= x["high"] for x in a)
    assert synthetic_bars("MX:CRAU26", 100, seed=8) != a


# ------------------------------------------------------------------- backtest
class _Buyer(Strategy):
    """Buys 1 lot on the first bar (limit above the high so it rests, then fills
    when a later bar trades up through it) and holds."""
    def on_start(self, ctx):
        self.done = False

    def on_bar(self, ctx, bar):
        if not self.done:
            ctx.buy(bar["symbol"], 1, bar["close"])   # resting limit at first close
            self.done = True


def test_backtest_fills_and_pnl_deterministic():
    bars = [
        {"symbol": "X", "start": 0, "open": 10, "high": 10, "low": 10, "close": 10,
         "volume": 5, "bid": 9.99, "ask": 10.01},
        {"symbol": "X", "start": 60, "open": 10, "high": 11, "low": 9, "close": 10.5,
         "volume": 5, "bid": 10.4, "ask": 10.5},   # trades through 10 -> buy fills @10
        {"symbol": "X", "start": 120, "open": 10.5, "high": 12, "low": 10.5,
         "close": 12, "volume": 5, "bid": 11.9, "ask": 12.0},
    ]
    r = run_backtest(_Buyer(), bars)
    assert r["orders"] == 1 and len(r["fills"]) == 1
    assert r["fills"][0]["price"] == 10 and r["positions"] == {"X": 1}
    # unrealized = (last mark 12 - avg 10) * 1
    assert r["realized_pnl"] == 0.0 and r["unrealized_pnl"] == 2.0
    assert r["total_pnl"] == 2.0
    assert run_backtest(_Buyer(), bars) == r        # reproducible


def test_backtest_ioc_immediate_or_cancel():
    class Marketable(Strategy):
        def on_bar(self, ctx, bar):
            if bar["start"] == 0:
                # buy above the market crosses (marketable -> fills at close);
                # sell above the market rests (ioc -> immediately canceled).
                ctx.buy(bar["symbol"], 2, bar["close"] + 5, tif="ioc")
                ctx.sell(bar["symbol"], 1, bar["close"] + 5, tif="ioc")

    bars = [{"symbol": "Y", "start": 0, "open": 100, "high": 100, "low": 100,
             "close": 100, "volume": 1, "bid": 99.9, "ask": 100.1}]
    r = run_backtest(Marketable(), bars)
    assert len(r["fills"]) == 1 and r["fills"][0]["price"] == 100  # only the buy filled
    assert r["positions"] == {"Y": 2}


# ------------------------------------------------------------- strategy loader
def test_load_strategy_from_file(tmp_path):
    p = tmp_path / "strat.py"
    p.write_text(
        "from qjtrader import Strategy\n"
        "class S(Strategy):\n"
        "    def on_bar(self, ctx, bar):\n"
        "        ctx.buy(bar['symbol'], 1, bar['close'])\n")
    strat = load_strategy(str(p))
    assert isinstance(strat, Strategy)
    r = run_backtest(strat, synthetic_bars("MX:CRAU26", 5, seed=1))
    assert r["orders"] >= 1


def test_load_strategy_missing_class(tmp_path):
    from qjtrader import QJError
    p = tmp_path / "empty.py"
    p.write_text("x = 1\n")
    with pytest.raises(QJError):
        load_strategy(str(p))


# ------------------------------------------------------------------ supervisor
class _FakeOrders:
    def __init__(self):
        self.sent = []
        self.cancel_all_called = False

    def order(self, **kw):
        self.sent.append(kw)

    def cancel(self, cid):
        self.sent.append({"cancel": cid})

    def replace(self, cid, **kw):
        self.sent.append({"replace": cid, **kw})

    def cancel_all(self):
        self.cancel_all_called = True


class _Recorder(Strategy):
    def __init__(self):
        self.events = []

    def on_start(self, ctx):
        self.events.append("start")

    def on_quote(self, ctx, q):
        self.events.append(("quote", q["symbol"]))
        ctx.buy("MX:CRAU26", 1, 97.0)          # tagged order

    def on_trade(self, ctx, t):
        self.events.append("trade")

    def on_fill(self, ctx, f):
        self.events.append(("fill", f.get("status")))

    def on_timer(self, ctx):
        self.events.append("timer")

    def on_stop(self, ctx):
        self.events.append("stop")


def test_supervisor_dispatch_tags_orders_and_tracks_fills():
    oe = _FakeOrders()
    strat = _Recorder()
    ctx = LiveContext(oe, strategy_tag="mr1")
    expected_cid = f"mr1-{ctx._context_token}-1"
    events = [
        ("md", {"type": "quote", "symbol": "MX:CRAU26", "data": {"bid": 96.9, "ask": 97.1}}),
        ("md", {"type": "trade", "symbol": "MX:CRAU26", "data": {"price": 97.0, "size": 3}}),
        ("timer", None),
        ("oe", {"type": "exec", "cid": expected_cid, "status": "filled",
                "last_qty": 1, "last_px": 97.0}),
    ]
    Supervisor(strat, ctx).run(events)
    assert strat.events[0] == "start" and strat.events[-1] == "stop"
    # order was placed with the strategy-tag cid prefix
    assert oe.sent[0]["cid"].startswith("mr1-") and oe.sent[0]["cid"].endswith("-1")
    assert oe.sent[0]["side"] == "buy"
    # exec updated the position book
    assert ctx.position("MX:CRAU26") == 1
    assert oe.cancel_all_called is True         # cancel-all on stop
    assert ctx.quote("MX:CRAU26") == {"bid": 96.9, "ask": 97.1}


def test_live_context_default_cids_are_unique_across_contexts_and_carry_actor():
    oe = _FakeOrders()
    actor = {"strategy_id": "mr", "strategy_version": "abc", "run_id": "run-1"}
    first = LiveContext(oe, strategy_tag="mr.abc", actor=actor)
    second = LiveContext(oe, strategy_tag="mr.abc", actor=actor)
    cid1 = first.buy("MX:CRAU26", 1, 97.0)
    cid2 = second.buy("MX:CRAU26", 1, 97.0)
    assert cid1 != cid2
    assert len(cid1) <= 32 and len(cid2) <= 32
    assert oe.sent[0]["actor"] == actor == oe.sent[1]["actor"]


# ------------------------------------------------------------------- CLI
def test_cli_backtest(tmp_path, capsys):
    from qjtrader._cli import main
    p = tmp_path / "s.py"
    p.write_text(
        "from qjtrader import Strategy\n"
        "class S(Strategy):\n"
        "    def on_bar(self, ctx, bar):\n"
        "        if ctx.position(bar['symbol'])==0: ctx.buy(bar['symbol'],1,bar['close'],tif='ioc')\n")
    rc = main(["backtest", str(p), "--symbol", "MX:CRAU26", "--bars", "30", "--seed", "3"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["bars"] == 30 and "total_pnl" in out
