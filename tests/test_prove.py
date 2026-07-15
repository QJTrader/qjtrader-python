"""`Client.prove()` (quote → resting order → cancel → journal) and `chain_stats()`."""
import pytest

from qjtrader.auth import TokenSource
from qjtrader.client import Client
from qjtrader.errors import QJError


@pytest.fixture(autouse=True)
def _fake_token(monkeypatch):
    monkeypatch.setattr(TokenSource, "token", lambda self: "faketoken")


class _FakeOrders:
    """A stand-in for a live `Orders` connection used to exercise `prove()`."""

    def __init__(self):
        self.placed = None
        self.canceled = None
        self._cid = "qj-abc123abcd"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def order(self, *, sym, side, qty, price, account="", tif="day"):
        self.placed = {"sym": sym, "side": side, "qty": qty,
                       "price": price, "account": account}
        return self._cid

    def cancel(self, orig_cid, cid=None):
        self.canceled = orig_cid
        return "qj-cancel00001"

    def updates(self, timeout=15.0):
        # First loop (pre-cancel): the resting order acks `new`.
        # Second loop (post-cancel): the cancel confirms `canceled`.
        if self.canceled is None:
            yield {"type": "order_update", "cid": self._cid, "status": "new"}
        else:
            yield {"type": "order_update", "cid": self._cid,
                   "orig_cid": self._cid, "status": "canceled"}


def test_prove_runs_full_lifecycle(monkeypatch):
    c = Client(client_id="a", client_secret="b")
    monkeypatch.setattr(c, "quote", lambda symbol, timeout=10.0: {
        "symbol": symbol, "bid": 100.0, "ask": 100.2,
        "bid_size": 5, "ask_size": 5, "source_type": "quote"})
    fake = _FakeOrders()
    monkeypatch.setattr(c, "orders", lambda: fake)
    monkeypatch.setattr(c, "events", lambda limit=200: {"events": [
        {"cid": fake._cid, "type": "order_update", "status": "canceled"},
        {"cid": "someone-else", "type": "order_update", "status": "new"},
    ]})

    out = c.prove("CA:RY", account="SIM")

    assert out["symbol"] == "CA:RY"
    assert out["cid"] == fake._cid
    assert out["cancel_cid"] == "qj-cancel00001"
    # A resting buy must sit *below* the bid so it never crosses/fills.
    assert fake.placed["side"] == "buy"
    assert fake.placed["price"] < 100.0
    assert fake.placed["account"] == "SIM"
    assert fake.canceled == fake._cid
    # Lifecycle captured both the resting ack and the cancel.
    statuses = [m["status"] for m in out["lifecycle"]]
    assert "new" in statuses and "canceled" in statuses
    # Journal is filtered to just this order's cid (not the other trader's).
    assert out["journal"] and all(e["cid"] == fake._cid for e in out["journal"])


def test_prove_raises_when_no_bid(monkeypatch):
    c = Client(client_id="a", client_secret="b")
    monkeypatch.setattr(c, "quote", lambda symbol, timeout=10.0: {
        "symbol": symbol, "bid": None, "ask": None, "source_type": "timeout"})
    with pytest.raises(QJError, match="no bid"):
        c.prove("CA:RY")


def test_chain_stats_hits_data_gateway_with_normalized_expiry():
    calls = []

    def opener(url, headers, method="GET", data=None):
        calls.append(url)
        return 200, b'{"put_call_ratio": 1.2, "oi_concentration": []}'

    c = Client(client_id="a", client_secret="b", rest_opener=opener)
    out = c.chain_stats("MX:RY", "2026-08-21")
    assert "data-feed.qjtrader.ai:8443/api/v1/chain/stats" in calls[0]
    assert "underlying=MX%3ARY" in calls[0]
    assert "expiry=202608" in calls[0]   # normalized client-side to YYYYMM
    assert out["put_call_ratio"] == 1.2
