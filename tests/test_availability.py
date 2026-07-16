from qjtrader import market_availability


def test_availability_is_provider_neutral_and_defensive_copy():
    first = market_availability()
    assert first["markets"]["US"]["limitations"]
    assert "SPY" in " ".join(first["markets"]["US"]["verified"])
    text = str(first).lower()
    assert "iqfeed" not in text
    first["markets"]["US"]["limitations"].clear()
    assert market_availability()["markets"]["US"]["limitations"]
