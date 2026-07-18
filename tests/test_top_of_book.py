from qjtrader.market_data import MarketData, top_of_book


def test_top_of_book_normalizes_snapshot():
    got = top_of_book({"type": "snapshot", "symbol": "CA:RY", "data": {
        "bids": [{"price": 201.1, "size": 300}],
        "asks": [{"price": 201.2, "size": 200}],
    }})
    assert got["bid"] == 201.1
    assert got["ask"] == 201.2
    assert got["bid_size"] == 300


def test_top_of_book_normalizes_quote():
    got = top_of_book({"type": "quote", "symbol": "CA:RY", "data": {
        "bid": 201.1, "ask": 201.2, "bid_size": 4, "ask_size": 5,
    }})
    assert got["bid"] == 201.1
    assert got["ask_size"] == 5


def test_real_consolidated_ca_quote_waits_for_official_cbbo():
    md = MarketData.__new__(MarketData)
    md.environment = "real"
    md.subscribe = lambda *_args, **_kwargs: None
    md.messages = lambda **_kwargs: iter([
        {"type": "level2", "symbol": "CA:CSU", "data": {"bids": [{"price": 2825.0}], "asks": [{"price": 2836.0}]}},
        {"type": "quote", "symbol": "CA:CSU", "data": {"bid": 0, "ask": 825500, "cbbo": False}},
        {"type": "quote", "symbol": "CA:CSU", "data": {"bid": 2825.5, "ask": 2834.23, "cbbo": True}},
    ])
    got = md.quote("CA:CSU")
    assert got["bid"] == 2825.5
    assert got["ask"] == 2834.23
    assert got["cbbo"] is True
