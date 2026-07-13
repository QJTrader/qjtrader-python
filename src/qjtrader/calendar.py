"""Operational calendar (plan §12.1) — front-month / expiry resolution.

The platform's own standing subscriptions (the house watchlist, the chain-snapshot
``CHAIN_TARGETS``, the hosted-runner symbol) and a strategy's ``on_roll`` all need
to name the *currently active* contract, not a hardcoded one that expires. MX rate
futures (CGB/CRA/BAX/SXF) trade the quarterly H/M/U/Z cycle; equity/index options
expire the 3rd Friday monthly.

These are self-contained date resolvers (no network). They are a sensible default;
the *authoritative* source is the exchange calendar / the instrument dictionary
(`hsvf.isinsymbol`), so treat a resolved contract as "roll to about here" and verify
against a live quote before trading a thin far-dated series.
"""
from __future__ import annotations

import datetime as _dt

_MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
               7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
_MONTH_ABBR = {3: "MAR", 6: "JUN", 9: "SEP", 12: "DEC",
               1: "JAN", 2: "FEB", 4: "APR", 5: "MAY", 7: "JUL", 8: "AUG",
               10: "OCT", 11: "NOV"}
_QUARTERLY = (3, 6, 9, 12)


def third_friday(year: int, month: int) -> _dt.date:
    """The 3rd Friday of a month — the standard monthly option/quarterly expiry."""
    first = _dt.date(year, month, 1)
    first_friday = 1 + (4 - first.weekday()) % 7
    return _dt.date(year, month, first_friday + 14)


def option_front_expiry(on: _dt.date | None = None) -> _dt.date:
    """The nearest monthly option expiry (3rd Friday) on/after `on`."""
    on = on or _dt.date.today()
    exp = third_friday(on.year, on.month)
    if exp < on:
        y, m = (on.year + on.month // 12, on.month % 12 + 1)
        exp = third_friday(y, m)
    return exp


def front_future(root: str, on: _dt.date | None = None, roll_days: int = 5) -> str:
    """The front-month contract for a quarterly MX future `root`, rolling `roll_days`
    before the contract's 3rd-Friday expiry. Returns a namespaced symbol,
    e.g. ``front_future("CGB")`` -> ``"MX:CGBU26"``."""
    on = on or _dt.date.today()
    for year in (on.year, on.year + 1):
        for m in _QUARTERLY:
            if third_friday(year, m) - _dt.timedelta(days=roll_days) > on:
                return f"MX:{root}{_MONTH_CODE[m]}{year % 100:02d}"
    raise ValueError(f"no front contract for {root} near {on}")


def futures_strip(root: str, n: int = 4, on: _dt.date | None = None) -> list[str]:
    """The next `n` quarterly contracts for `root`, front to back (the strip)."""
    on = on or _dt.date.today()
    out: list[str] = []
    for year in (on.year, on.year + 1, on.year + 2):
        for m in _QUARTERLY:
            if third_friday(year, m) > on:
                out.append(f"MX:{root}{_MONTH_CODE[m]}{year % 100:02d}")
                if len(out) >= n:
                    return out
    return out


def option_symbol(root: str, expiry: _dt.date, strike: float, cp: str) -> str:
    """Build a namespaced MX equity-option symbol for the demand-driven O1 feed:
    ``ROOT + YY + MON + STRIKE + C/P + DD`` (see qj-symbology). `cp` is 'C' or 'P'."""
    strike_s = f"{strike:g}"
    return (f"MX:{root}{expiry.year % 100:02d}{_MONTH_ABBR[expiry.month]}"
            f"{strike_s}{cp.upper()}{expiry.day:02d}")


def roll_needed(symbol: str, on: _dt.date | None = None, roll_days: int = 5) -> bool:
    """True if a quarterly future `symbol` (e.g. ``MX:CGBU26``) is within `roll_days`
    of expiry (or past it) — the signal a strategy/house-list should roll to the next.
    Unrecognised symbols return False (nothing to roll)."""
    on = on or _dt.date.today()
    if not symbol.startswith("MX:"):
        return False
    body = symbol[3:]
    code = next((c for c in reversed(body) if c in _MONTH_CODE.values()), None)
    if code is None or not body[-2:].isdigit():
        return False
    month = next(m for m, c in _MONTH_CODE.items() if c == code)
    year = 2000 + int(body[-2:])
    return third_friday(year, month) - _dt.timedelta(days=roll_days) <= on
