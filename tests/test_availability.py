from qjtrader import market_availability


def test_availability_is_provider_neutral_and_defensive_copy():
    first = market_availability()
    assert first["markets"]["US"]["limitations"]
    assert "SPY" in " ".join(first["markets"]["US"]["verified"])
    verified = " ".join(first["markets"]["US"]["verified"])
    assert all(symbol in verified for symbol in ("US:@USU26", "US:@TYU26", "US:@FVU26"))
    text = str(first).lower()
    assert "iqfeed" not in text
    first["markets"]["US"]["limitations"].clear()
    assert market_availability()["markets"]["US"]["limitations"]


def test_availability_is_product_and_environment_specific():
    out = market_availability()
    assert "order_bids" in out["data_shapes"]["equity_book"]
    assert "odd_order_bids" in out["data_shapes"]["equity_book"]
    assert "venue_state" in out["observation_contract"]["provenance"]
    assert "provenance" in out["observation_contract"]
    assert "implied depth" in out["products"]["mx_future"]["production"]["data"]
    assert out["products"]["us_future"]["sandbox"]["data"].startswith("synthetic")
    assert out["products"]["us_future"]["verified_symbols"][-3:] == [
        "US:@USU26", "US:@TYU26", "US:@FVU26"
    ]
    assert "symbol-dependent" in out["products"]["us_equity_etf"]["production"]["data"]
    assert "unavailable" in out["products"]["tsx_index"]["production"]["data"]
    assert out["products"]["forex"]["symbol"] is None
    assert "null prices" in out["observation_contract"]["unquoted"]
    assert "never falls back" in out["observation_contract"]["history"]
    assert "not_recorded" in out["observation_contract"]["history_empty"]
    assert "source-dependent" in out["data_shapes"]["derivative_book"]
