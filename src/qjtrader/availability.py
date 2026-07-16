"""User-facing QJ cloud API availability, kept provider-neutral.

This is deliberately offline metadata: callers and AI tools can inspect the
supported boundary before opening a market-data or order connection.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_AVAILABILITY: dict[str, Any] = {
    "as_of": "2026-07-16",
    "reference": "https://docs.qjtrader.ai/docs/ai/availability",
    "access_note": (
        "Sandbox access is self-serve. Live data and production order entry "
        "depend on the entitlements and accounts attached to your credential."
    ),
    "markets": {
        "CA": {
            "instruments": "Canadian equities, ETFs and stock-like listings",
            "market_data": "L1 and consolidated/per-venue L2; official CBBO",
            "orders": "Available across supported lit, dark and smart routes",
            "examples": ["CA:RY", "CA:RY.PT"],
            "limitations": ["TSX index values are not currently available"],
        },
        "MX": {
            "instruments": "Montréal Exchange futures and listed options",
            "market_data": "Futures L1/L2; listed-option L1",
            "orders": "Futures and listed options available by account entitlement",
            "examples": ["MX:CGBU26", "MX:AAPL26AUG33C21"],
            "limitations": [
                "Some thin or seasonal contracts may have no current quote",
                "Strategy and options-on-futures availability depends on an active market",
            ],
        },
        "US": {
            "instruments": "US equities/ETFs, listed options and selected futures",
            "market_data": (
                "Equity/ETF L1; symbol-dependent equity/ETF L2; listed-option L1 "
                "when emitted; selected futures L1/L2"
            ),
            "orders": (
                "US equities, listed options and selected futures are available "
                "to credentials linked to the corresponding gateway accounts"
            ),
            "examples": ["US:AAPL", "US:SPY", "US:@ESU26"],
            "verified": [
                "US:AAPL L1 and equity order entry",
                "US:SPY L1/L2",
                "US:@ESU26 L1/L2 and futures order entry",
                "US listed-option L1 and order entry on entitled contracts",
            ],
            "limitations": [
                "US equity depth is symbol-dependent: SPY is verified; AAPL L2 is not currently emitted",
                "NDX index L1/L2 is not currently available",
                "US listed-option depth is not currently available",
                "A successful subscription can be silent when the upstream market does not emit that product",
            ],
        },
    },
}


def market_availability() -> dict[str, Any]:
    """Return a copy of the current market-data and order-entry support matrix."""
    return deepcopy(_AVAILABILITY)

