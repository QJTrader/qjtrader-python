"""Book-native L2 backtest with queue-honest fills (plan §10.3/§8)."""
from qjtrader import (L2Context, Strategy, run_l2_backtest, synthetic_l2_events)


def _book(sym, bids, asks, ts=0.0):
    return {"type": "level2", "symbol": sym, "ts": ts,
            "data": {"bids": [{"price": p, "size": s} for p, s in bids],
                     "asks": [{"price": p, "size": s} for p, s in asks]}}


def _trade(sym, price, size, ts=0.0):
    return {"type": "trade", "symbol": sym, "ts": ts, "data": {"price": price, "size": size}}


BOOK = ([(98.9, 4), (98.0, 10)], [(100.0, 5), (100.1, 10)])


# ------------------------------------------------------------- marketable
class _MarketBuyOnce(Strategy):
    def on_start(self, ctx):
        self.done = False

    def on_depth(self, ctx, ev):
        if not self.done:
            self.done = True
            ctx.buy(ev["symbol"], int(ctx.param("qty", 3)), ctx.param("px"), tif="ioc")


def test_marketable_walks_book():
    events = [_book("X", *BOOK)]
    # limit 100.15 crosses BOTH ask levels -> 5 @ 100.0 then 3 @ 100.1 = 8
    r = run_l2_backtest(_MarketBuyOnce(), events, params={"qty": 8, "px": 100.15})
    prices = [(f["qty"], f["price"]) for f in r["fills"]]
    assert prices == [(5, 100.0), (3, 100.1)]
    assert r["positions"] == {"X": 8}
    assert r["fills"][0]["fill_model"] == "queue-v1"


def test_marketable_limit_caps_at_its_price():
    # limit 100.05 only crosses the 100.0 level; ioc cancels the rest (honest)
    r = run_l2_backtest(_MarketBuyOnce(), [_book("X", *BOOK)], params={"qty": 8, "px": 100.05})
    assert [(f["qty"], f["price"]) for f in r["fills"]] == [(5, 100.0)]
    assert r["positions"] == {"X": 5}


def test_fok_all_or_none():
    events = [_book("X", *BOOK)]
    r = run_l2_backtest(_MarketBuyOnce(), events, params={"qty": 100, "px": 100.05})
    # only 5+10=15 available at/through 100.05? 100.1 > 100.05 so only 5 acceptable;
    # but this strategy uses ioc — switch: fok with qty>available fills nothing.

    class Fok(Strategy):
        def on_depth(self, ctx, ev):
            ctx.buy("X", 100, 100.05, tif="fok")

    r2 = run_l2_backtest(Fok(), [_book("X", *BOOK)])
    assert r2["fills"] == [] and r2["positions"] == {}


# --------------------------------------------------- passive + trade-through
class _PassiveBuy(Strategy):
    def on_start(self, ctx):
        self.placed = False

    def on_depth(self, ctx, ev):
        if not self.placed:
            self.placed = True
            ctx.buy(ev["symbol"], 3, 98.9, tif="day")  # joins the bid (queue ahead = 4)


def test_passive_fills_after_queue_then_trade_through():
    events = [
        _book("X", *BOOK, ts=0),
        _trade("X", 98.9, 2, ts=1),   # eats 2 of the 4 ahead -> no fill
        _trade("X", 98.5, 5, ts=2),   # clears the remaining 2, then fills our 3
    ]
    r = run_l2_backtest(_PassiveBuy(), events)
    assert len(r["fills"]) == 1
    assert r["fills"][0]["qty"] == 3 and r["fills"][0]["price"] == 98.9
    assert r["positions"] == {"X": 3}


def test_passive_no_fill_without_trade_through():
    events = [_book("X", *BOOK, ts=0), _trade("X", 99.5, 100, ts=1)]  # above our bid
    r = run_l2_backtest(_PassiveBuy(), events)
    assert r["fills"] == [] and r["positions"] == {}


# ------------------------------------------------------ synthetic + determinism
def test_synthetic_l2_deterministic_and_runs():
    a = synthetic_l2_events("MX:CRAU26", 50, seed=4)
    b = synthetic_l2_events("MX:CRAU26", 50, seed=4)
    assert a == b
    assert any(e["type"] == "level2" for e in a)

    class Taker(Strategy):
        def on_trade(self, ctx, ev):
            if ctx.position(ev["symbol"]) == 0:
                q = ctx.quote(ev["symbol"])
                if q and q["ask"]:
                    ctx.buy(ev["symbol"], 1, q["ask"], tif="ioc")

    r1 = run_l2_backtest(Taker(), synthetic_l2_events("MX:CRAU26", 50, seed=4))
    r2 = run_l2_backtest(Taker(), synthetic_l2_events("MX:CRAU26", 50, seed=4))
    assert r1 == r2                       # reproducible
    assert r1["events"] > 0 and "total_pnl" in r1


def test_quote_reads_top_of_book():
    ctx = L2Context({}, Strategy())
    ctx.books["X"] = {"bids": [{"price": 98.9, "size": 4}], "asks": [{"price": 100.0, "size": 5}]}
    assert ctx.quote("X") == {"bid": 98.9, "ask": 100.0, "last": None}
