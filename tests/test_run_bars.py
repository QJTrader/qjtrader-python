"""Live bar synthesis (run.Supervisor with bar_interval): bar-driven strategies
must run on the live/paper tick stream exactly as in the backtest."""
import threading

from qjtrader.run import LiveContext, Supervisor, _BarBuilder, run_strategy_live, strategy_version
from qjtrader.strategy import Strategy


def test_strategy_version_stable_and_param_sensitive():
    s = _RecordingStrategy()
    v1 = strategy_version(s, {"edge": 0.02})
    assert v1 == strategy_version(s, {"edge": 0.02})       # deterministic
    assert len(v1) == 8 and all(c in "0123456789abcdef" for c in v1)
    assert v1 != strategy_version(s, {"edge": 0.03})       # params change the version

    class _Other(Strategy):
        def on_bar(self, ctx, bar):
            self.x = 1                                       # different source
    assert strategy_version(_Other(), {"edge": 0.02}) != v1  # code change → new version


class _FakeOE:
    def __init__(self):
        self.sent = []

    def order(self, **kw):
        self.sent.append(kw)

    def cancel(self, cid):
        pass

    def replace(self, cid, **kw):
        pass

    def cancel_all(self):
        pass


class _RecordingStrategy(Strategy):
    def __init__(self):
        self.bars = []

    def on_bar(self, ctx, bar):
        self.bars.append(bar)


def _md_trade(sym, px, sz):
    return ("md", {"type": "trade", "symbol": sym, "data": {"price": px, "size": sz}})


def _md_quote(sym, bid, ask):
    return ("md", {"type": "quote", "symbol": sym, "data": {"bid": bid, "ask": ask}})


def test_bar_builder_ohlcv_from_trades():
    clk = [0.0]
    bb = _BarBuilder(5.0, clock=lambda: clk[0])
    bb.on_trade("X", 100.0, 2, 0.0)
    bb.on_trade("X", 101.0, 1, 1.0)
    bb.on_trade("X", 99.5, 3, 2.0)
    assert bb.roll(4.0) == []            # bucket 0 not elapsed yet
    bars = bb.roll(6.0)                   # now past the 5s boundary
    assert len(bars) == 1
    b = bars[0]
    assert (b["open"], b["high"], b["low"], b["close"], b["volume"]) == (100.0, 101.0, 99.5, 99.5, 6.0)
    assert b["symbol"] == "X"


def test_bar_uses_quote_mid_when_no_trades():
    bb = _BarBuilder(5.0)
    bb.on_quote("Y", 10.0, 10.2, 0.0)    # mid 10.1, no trades
    bars = bb.roll(6.0)
    assert len(bars) == 1 and bars[0]["close"] == 10.1
    # a bar with neither trade nor quote is dropped, not emitted as junk
    bb.on_trade("Z", 5.0, 1, 0.0)
    bb._cur["Q"] = {"symbol": "Q", "_bucket": 0.0, "open": None, "high": None,
                    "low": None, "close": None, "volume": 0.0}
    syms = {b["symbol"] for b in bb.roll(6.0)}
    assert "Z" in syms and "Q" not in syms


def test_supervisor_synthesizes_bars_live():
    clk = [0.0]
    oe = _FakeOE()
    ctx = LiveContext(oe, strategy_tag="t", clock=lambda: clk[0])
    strat = _RecordingStrategy()
    sup = Supervisor(strat, ctx, bar_interval=5.0, clock=lambda: clk[0])
    sup.start()
    sup.dispatch(*_md_trade("MX:CGBU26", 119.5, 2))
    clk[0] = 1.0
    sup.dispatch(*_md_trade("MX:CGBU26", 119.6, 1))
    clk[0] = 6.0
    sup.dispatch("timer", None)          # boundary crossed → on_bar fires
    assert len(strat.bars) == 1
    assert strat.bars[0]["close"] == 119.6 and strat.bars[0]["volume"] == 3.0


def test_on_fill_only_fires_for_real_fills():
    """accepted/new/rejected order updates must NOT reach on_fill (backtest parity):
    a strategy that frees an order slot on its cid would misfire on the 'accepted'
    echo and re-quote every bar otherwise."""
    class _FillRec(Strategy):
        def __init__(self):
            self.fills = []
        def on_fill(self, ctx, f):
            self.fills.append(f.get("status"))
    ctx = LiveContext(_FakeOE(), strategy_tag="t")
    strat = _FillRec()
    sup = Supervisor(strat, ctx)
    sup.start()
    for status, typ in [("accepted", "order_update"), ("new", "order_update"),
                        ("rejected", "order_update")]:
        sup.dispatch("oe", {"type": typ, "cid": "t-1", "status": status})
    assert strat.fills == []                       # none of those are fills
    sup.dispatch("oe", {"type": "exec", "cid": "t-1", "status": "filled",
                        "last_qty": 1, "last_px": 100.0})
    assert strat.fills == ["filled"]               # only the real fill


def test_bars_roll_on_md_events_not_only_timers():
    """Under load the merge queue never drains, so timer ticks are starved; bars
    must still roll on ordinary md events or bar strategies never fire live."""
    clk = [0.0]
    ctx = LiveContext(_FakeOE(), strategy_tag="t", clock=lambda: clk[0])
    strat = _RecordingStrategy()
    sup = Supervisor(strat, ctx, bar_interval=5.0, clock=lambda: clk[0])
    sup.start()
    sup.dispatch(*_md_trade("X", 100.0, 1))
    clk[0] = 7.0
    sup.dispatch(*_md_trade("X", 101.0, 1))   # an md event, NOT a timer, past the boundary
    assert len(strat.bars) == 1 and strat.bars[0]["close"] == 100.0


def test_supervisor_bar_synthesis_off_by_default():
    ctx = LiveContext(_FakeOE(), strategy_tag="t")
    strat = _RecordingStrategy()
    sup = Supervisor(strat, ctx)         # no bar_interval → no synthesis
    sup.start()
    sup.dispatch(*_md_trade("X", 1.0, 1))
    sup.dispatch("timer", None)
    assert strat.bars == []


def test_restart_hydration_seeds_position_and_clears_stale_orders():
    """On (re)connect a run must start from the gateway's TRUE position, not a fresh
    zero (§10.1). Hydrate net from /positions and clear stale working orders."""
    stop = threading.Event()
    cancels = [0]

    class _MD:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def subscribe(self, _s):
            pass
        def messages(self, timeout=None):
            stop.set()                      # end the run right after connect
            return iter(())

    class _OE:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def updates(self, timeout=None):
            return iter(())
        def cancel_all(self):
            cancels[0] += 1
        def order(self, **_k):
            pass
        def cancel(self, _c):
            pass
        def replace(self, _c, **_k):
            pass

    class _Client:
        def market_data(self):
            return _MD()
        def orders(self):
            return _OE()
        def positions(self):
            return {"positions": {"MX:X": 3, "MX:Y": -2, "MX:Z": 0}}

    seen = {}

    class _Probe(Strategy):
        def on_start(self, ctx):
            seen["X"] = ctx.position("MX:X")
            seen["Y"] = ctx.position("MX:Y")
            seen["Z"] = ctx.position("MX:Z")

    run_strategy_live(_Client(), _Probe(), symbols=["MX:X"], stop=stop, reconnect=False)
    assert seen == {"X": 3, "Y": -2, "Z": 0}   # long/short net restored; flat stays flat
    assert cancels[0] >= 1                       # stale working orders cleared on start


def test_restart_hydration_prefers_broker_total_over_fill_only():
    """When the gateway exposes broker-truth positions_detail (real plane, oms-
    positions-plan.md §3.4), hydration must seed TotalVolume = InitVolume + NetVolume,
    not the fill-only net. A strategy that inherited a broker start-of-day position
    would otherwise resume understated by exactly that InitVolume."""
    stop = threading.Event()

    class _MD:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def subscribe(self, _s):
            pass
        def messages(self, timeout=None):
            stop.set()
            return iter(())

    class _OE:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def updates(self, timeout=None):
            return iter(())
        def cancel_all(self):
            pass
        def order(self, **_k):
            pass
        def cancel(self, _c):
            pass
        def replace(self, _c, **_k):
            pass

    class _Client:
        def market_data(self):
            return _MD()
        def orders(self):
            return _OE()
        def positions(self):
            # MX:X: broker short 2 + fill +1 => total -1 (fill-only would say +1).
            # MX:W: no broker row => falls back to the fill-only net (+4).
            return {
                "positions": {"MX:X": 1, "MX:W": 4},
                "positions_detail": {
                    "MX:X": {"broker_qty": -2, "fill_qty": 1, "total_qty": -1},
                },
            }

    seen = {}

    class _Probe(Strategy):
        def on_start(self, ctx):
            seen["X"] = ctx.position("MX:X")
            seen["W"] = ctx.position("MX:W")

    run_strategy_live(_Client(), _Probe(), symbols=["MX:X"], stop=stop, reconnect=False)
    assert seen == {"X": -1, "W": 4}   # broker total for X; fill-only fallback for W


def test_restart_hydration_includes_broker_only_position():
    from qjtrader.run import _hydrate_context
    class Client:
        def positions(self):
            return {"positions": {}, "positions_detail": {
                "CA:RY": {"broker_qty": 25, "fill_qty": 0, "total_qty": 25}}}
    class Orders:
        def cancel_all(self): pass
    ctx = LiveContext(Orders(), account="")
    _hydrate_context(Client(), ctx)
    assert ctx.position("CA:RY") == 25


def test_run_reconnects_on_stream_drop():
    """A dropped stream must not kill a run: merge_streams ends (dead detection) and
    run_strategy_live re-opens the connection until stop is set. If reconnect or the
    death detection were broken, the run would hang on the first connect and never
    re-open — the join-timeout + connect count catch both."""
    stop = threading.Event()
    connects = [0]

    class _MD:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def subscribe(self, _syms):
            pass
        def messages(self, timeout=None):
            yield {"type": "quote", "symbol": "X", "data": {"bid": 1, "ask": 2}}
            raise ConnectionError("dropped")     # simulate a gateway disconnect

    class _OE:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def updates(self, timeout=None):
            raise ConnectionError("dropped")
        def cancel_all(self):
            pass
        def order(self, **_k):
            pass
        def cancel(self, _c):
            pass
        def replace(self, _c, **_k):
            pass

    class _Client:
        def market_data(self):
            connects[0] += 1
            if connects[0] >= 3:
                stop.set()                        # let it re-open a couple times
            return _MD()
        def orders(self):
            return _OE()

    t = threading.Thread(target=lambda: run_strategy_live(
        _Client(), _RecordingStrategy(), symbols=["X"], stop=stop,
        timer_s=0.02, reconnect_backoff_s=0.01))
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "run did not terminate — reconnect/merge hang"
    assert connects[0] >= 3, f"expected multiple reconnects, got {connects[0]}"
