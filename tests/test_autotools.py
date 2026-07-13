"""Auto-tools (§10.2), the run registry (§10.3), and scenario/positions REST reads."""
import threading
import time

import pytest

from qjtrader import (AUTO_TOOLS, Client, RunRegistry, make_auto_tool,
                      run_backtest, synthetic_bars)
from qjtrader.auth import TokenSource


# --------------------------------------------------------------- auto-tools
def test_scalper_registered_and_backtests():
    assert "scalper" in AUTO_TOOLS
    strat = make_auto_tool("scalper")
    bars = synthetic_bars("MX:CRAU26", 300, seed=11)
    r = run_backtest(strat, bars, params={"symbol": "MX:CRAU26", "edge": 0.01,
                                          "target": 0.01, "max_position": 2})
    # a scalper on a mean-reverting series should trade and stay within its cap
    assert r["orders"] > 0 and len(r["fills"]) > 0
    assert abs(r["positions"].get("MX:CRAU26", 0)) <= 2
    assert "total_pnl" in r


def test_make_auto_tool_unknown():
    with pytest.raises(KeyError):
        make_auto_tool("nope")


# --------------------------------------------------------------- run registry
def test_run_registry_start_status_stop():
    started = threading.Event()

    def fake_runner(client, strategy, *, symbols, params, account, strategy_tag, stop):
        started.set()
        stop.wait(timeout=2.0)          # block until asked to stop

    reg = RunRegistry(runner=fake_runner)
    st = reg.start(client=object(), strategy=object(), symbols=["MX:X"], tag="s1")
    run_id = st["id"]
    assert started.wait(1.0)
    assert reg.status(run_id)["status"] in ("running", "starting")
    assert reg.status(run_id)["tag"] == "s1"
    assert "_stop" not in reg.status(run_id)     # internals not leaked
    reg.stop(run_id)
    for _ in range(50):
        if reg.status(run_id)["status"] == "stopped":
            break
        time.sleep(0.02)
    assert reg.status(run_id)["status"] == "stopped"
    assert len(reg.status()["runs"]) == 1


def test_run_registry_reports_error():
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    reg = RunRegistry(runner=boom)
    st = reg.start(client=None, strategy=None, symbols=["X"])
    for _ in range(50):
        if reg.status(st["id"])["status"] == "error":
            break
        time.sleep(0.02)
    assert reg.status(st["id"])["status"] == "error"
    assert "kaboom" in reg.status(st["id"])["error"]


# --------------------------------------------------- scenario/positions client
@pytest.fixture
def _fake_token(monkeypatch):
    monkeypatch.setattr(TokenSource, "token", lambda self: "t")


def test_client_set_scenario_posts(_fake_token):
    seen = {}

    def opener(url, headers, method="GET", data=None):
        seen["url"], seen["method"], seen["data"] = url, method, data
        return 200, b'{"scenario": "fast", "expires_in": 30.0}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    out = c.set_scenario("fast", symbol="MX:X", seconds=30)
    assert out["scenario"] == "fast"
    assert seen["method"] == "POST" and "/api/v1/scenario" in seen["url"]
    assert b'"name": "fast"' in seen["data"]


def test_client_positions_gets(_fake_token):
    def opener(url, headers, method="GET", data=None):
        return 200, b'{"type":"envelope","positions":{"MX:X":3}}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    assert c.positions()["positions"] == {"MX:X": 3}
