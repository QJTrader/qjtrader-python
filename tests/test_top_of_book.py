from qjtrader.market_data import top_of_book


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
