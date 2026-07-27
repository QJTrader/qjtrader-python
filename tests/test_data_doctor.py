from qjtrader.data_doctor import inspect_stream
from qjtrader.market_data import MarketData


class FakeStream:
    environment = "real"
    user = "production-client"

    def __init__(self, messages):
        self.out = []
        self._messages = messages

    def subscribe(self, symbols, depth=None, venues=None):
        self.out.append({
            "symbols": list(symbols),
            "depth": depth,
            "venues": venues,
        })

    def messages(self, **_kwargs):
        return iter(self._messages)


def test_data_doctor_separates_gateway_and_customer_timing():
    published = 1_000_000_000
    stream = FakeStream([
        {
            "type": "subscription_plan",
            "expanded_symbols": ["CA:AW", "CA:AW.PT"],
        },
        {
            "type": "quote",
            "symbol": "CA:AW",
            "data": {"cbbo": True, "bid": 42.0, "ask": 42.1},
            "meta": {
                "transport_age_ms": 12.5,
                "server_publish_ns": published,
                "stale": False,
                "cached_snapshot": True,
                "snapshot_age_ms": 1234.5,
            },
        },
        {
            "type": "venue_state",
            "symbol": "CA:AW.PT",
            "data": {
                "transport_current": True,
                "book_initialized": True,
                "book_epoch": 7,
            },
            "meta": {
                "transport_age_ms": 13.5,
                "server_publish_ns": published,
                "stale": False,
            },
        },
    ])
    report = inspect_stream(
        stream,
        ["CA:AW"],
        all_venues=True,
        clock_ns=lambda: published + 20_000_000,
    )
    assert stream.out == [{
        "symbols": ["CA:AW"],
        "depth": 10,
        "venues": "all_entitled",
    }]
    assert report["status"] == "READY"
    assert report["symbols"]["CA:AW"]["official_cbbo"] == 1
    assert report["symbols"]["CA:AW"]["transport_age_ms"]["p50"] == 12.5
    assert report["symbols"]["CA:AW"]["customer_receive_age_ms"]["p50"] == 20.0
    assert report["symbols"]["CA:AW"]["cached_snapshots"] == 1
    assert report["symbols"]["CA:AW"]["max_snapshot_age_ms"] == 1234.5


def test_data_doctor_fails_closed_on_stale_truncated_or_missing_data():
    stream = FakeStream([
        {
            "type": "subscription_plan",
            "expanded_symbols": ["CA:CSU", "CA:CSU.PT", "CA:CSU.TO"],
        },
        {
            "type": "level2",
            "symbol": "CA:CSU.PT",
            "data": {
                "odd_order_depth": {
                    "bid_truncated": True,
                    "ask_truncated": False,
                },
            },
            "meta": {"stale": True},
        },
    ])
    report = inspect_stream(stream, ["CA:CSU"], all_venues=True)
    assert report["status"] == "STALE"
    assert report["stale_symbols"] == ["CA:CSU.PT"]
    assert report["truncated_symbols"] == ["CA:CSU.PT"]
    assert report["missing_symbols"] == ["CA:CSU", "CA:CSU.TO"]


def test_market_data_all_venues_uses_public_contract():
    stream = MarketData.__new__(MarketData)
    sent = []
    stream.send = sent.append
    stream.subscribe_all_venues(["CA:FFH"], depth=10)
    assert sent == [{
        "action": "subscribe",
        "symbols": ["CA:FFH"],
        "depth": 10,
        "venues": "all_entitled",
    }]
