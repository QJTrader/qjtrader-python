"""Operational calendar (§12.1) — front-month / expiry resolution."""
import datetime as dt
from qjtrader.calendar import (third_friday, option_front_expiry, front_future,
                               futures_strip, roll_needed, option_symbol)


def test_third_friday():
    assert third_friday(2026, 9) == dt.date(2026, 9, 18)   # Sep 2026 3rd Fri
    assert third_friday(2026, 7) == dt.date(2026, 7, 17)


def test_front_future_matches_live_contract():
    on = dt.date(2026, 7, 13)
    # Jun-2026 (M) already rolled; Sep-2026 (U) is the front — matches the live house symbol
    assert front_future("CGB", on) == "MX:CGBU26"
    assert front_future("CRA", on) == "MX:CRAU26"
    # right at the Sep roll date it advances to Dec (Z)
    assert front_future("CGB", dt.date(2026, 9, 14)) == "MX:CGBZ26"


def test_futures_strip_front_to_back():
    strip = futures_strip("CGB", 3, dt.date(2026, 7, 13))
    assert strip == ["MX:CGBU26", "MX:CGBZ26", "MX:CGBH27"]


def test_option_front_expiry():
    assert option_front_expiry(dt.date(2026, 7, 13)) == dt.date(2026, 7, 17)
    # after this month's expiry, roll to next month's 3rd Friday
    assert option_front_expiry(dt.date(2026, 7, 20)) == dt.date(2026, 8, 21)


def test_roll_needed():
    assert roll_needed("MX:CGBU26", dt.date(2026, 9, 15)) is True    # within 5d of Sep 18
    assert roll_needed("MX:CGBU26", dt.date(2026, 7, 13)) is False   # months away
    assert roll_needed("CA:RY", dt.date(2026, 7, 13)) is False       # not a future


def test_option_symbol():
    assert option_symbol("AAPL", dt.date(2026, 8, 21), 44.5, "C") == "MX:AAPL26AUG44.5C21"
