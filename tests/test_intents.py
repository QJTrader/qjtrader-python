"""Intent-diff (§8 shadow regression / L1): compare two version tags' order intents
from the journal, decision-for-decision."""
from qjtrader.intents import intent_diff


def _acc(cid, sym, side, qty, price, ts):
    return {"type": "order_update", "status": "accepted", "cid": cid,
            "sym": sym, "side": side, "qty": qty, "price": price, "ts": ts}


def test_intent_diff_identical_versions():
    ev = [
        _acc("mr.v1-1", "MX:CGBU26", "buy", 1, 119.0, "t1"),
        _acc("mr.v2-1", "MX:CGBU26", "buy", 1, 119.0, "t1"),
        _acc("mr.v1-2", "MX:CGBU26", "sell", 1, 119.1, "t2"),
        _acc("mr.v2-2", "MX:CGBU26", "sell", 1, 119.1, "t2"),
    ]
    d = intent_diff(ev, "mr.v1", "mr.v2")
    assert d["identical"] and d["matched"] == 2 and not d["differing"]


def test_intent_diff_flags_divergence_and_extras():
    ev = [
        _acc("mr.v1-1", "MX:CGBU26", "buy", 1, 119.0, "t1"),
        _acc("mr.v2-1", "MX:CGBU26", "buy", 2, 119.0, "t1"),   # qty differs at seq 1
        _acc("mr.v1-2", "MX:CGBU26", "sell", 1, 119.1, "t2"),  # v1-only (seq 2)
        _acc("mr.v2-3", "MX:CGBU26", "buy", 1, 118.9, "t3"),   # v2-only (seq 3)
    ]
    d = intent_diff(ev, "mr.v1", "mr.v2")
    assert not d["identical"]
    assert len(d["differing"]) == 1 and d["differing"][0]["seq"] == "1"
    assert d["differing"][0]["a"]["qty"] == 1 and d["differing"][0]["b"]["qty"] == 2
    assert [i["cid"] for i in d["a_only"]] == ["mr.v1-2"]
    assert [i["cid"] for i in d["b_only"]] == ["mr.v2-3"]
    # only accepted events count; fills/other statuses are ignored
    assert intent_diff(ev + [{"status": "filled", "cid": "mr.v1-9"}], "mr.v1", "mr.v2")["matched"] == d["matched"]
