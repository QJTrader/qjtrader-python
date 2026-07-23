"""User-facing QJ cloud API availability, kept provider-neutral.

This is deliberately offline metadata: callers and AI tools can inspect the
supported boundary before opening a market-data or order connection.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_AVAILABILITY: dict[str, Any] = {
    "as_of": "2026-07-23",
    "reference": "https://docs.qjtrader.ai/docs/ai/availability",
    "access_note": (
        "Sandbox access is self-serve. Live data and production order entry "
        "depend on the entitlements and accounts attached to your credential."
    ),
    "environment_guide": {
        "sandbox": "Self-serve, synthetic and 24/7. It accepts CA:, MX: and US: product grammars but does not prove a production entitlement.",
        "production": "Real data and orders are independently permissioned by market, product, account and route. A quote never implies order authority or L2 availability.",
        "recommended_check": "Read the product's sandbox and production fields, then session_info for this credential.",
    },
    "observation_contract": {
        "aggregated_book": "snapshot.data.bids/asks contain rounded Top5; Canadian equity snapshots add full-size odd_lot_* and special_lot_* views, bounded price-window order_bids/order_asks, and depth-independent odd_order_bids/odd_order_asks with explicit odd_order_depth truncation; additive views must not be summed into Top5",
        "provenance": "live messages carry meta.source, meta.venue, meta.sequence, agent_recv_ns, server_publish_ns, published_at, transport_age_ms, stale_reason and stale so consumers can detect an uplink backlog; an initial cached book also carries cached_snapshot and snapshot_age_ms; lightweight venue_state messages reaffirm exact-venue transport/book liveness without one venue validating another",
        "events": "market_event messages preserve exchange state, auctions, MOC, RFQ, reference, schedule and correction records; branch on data.event and render only fields present",
        "summary_quote": "quote.data can add last, change, fractional percent_change, volume, high, low and source",
        "unquoted": "a valid subscription can return null prices or remain quiet; this means unquoted now, not price zero",
        "history": "history.source is synthetic in sandbox, recorded for captured production observations, or unavailable; production never falls back to generated bars",
        "history_empty": "availability=not_recorded with an empty bars array is an honest production result, not a connectivity failure and not permission to draw a synthetic chart",
        "market_memory": "production bars are captured automatically while a symbol is observed; a continuous pin keeps a standing watch and richer market-event capture after user apps disconnect; sandbox history is regenerated and never stored",
        "honesty_rule": "render only fields present; never infer Greeks, terms, NAV, depth, or order authority from security type",
    },
    "data_shapes": {
        "equity_book": "price-aggregated rounded Top5 plus full-size odd-lot and special-lot arrays, bounded order_bids/order_asks price-window rows, and depth-independent odd_order_bids/odd_order_asks rows with stable native identity, best_odd_bid/best_odd_ask and explicit odd_order_depth truncation; sparse listings can be one-sided",
        "derivative_book": "price/size depth with source-dependent order counts and explicit implied levels where emitted",
        "option_quote": "top-of-book or unquoted state; chain analytics are separate and may be absent in production",
        "package_quote": "episodic package quote; leg prices and exchange ratios must not be assumed",
    },
    "products": {
        "ca_equity": {"plain_name": "Canadian common share", "symbol": "CA:RY", "sandbox": {"data": "synthetic L1 + five-level venue-shaped L2", "orders": "simulated"}, "production": {"data": "official CBBO + five-level consolidated and deeper venue price views, QJ/TMX order-level TL2 rows, and depth-independent odd-order overlays", "orders": "lit, dark and smart routes; entitled accounts"}},
        "ca_etf": {"plain_name": "Canadian exchange-traded fund", "symbol": "CA:XIU", "sandbox": {"data": "synthetic L1/L2", "orders": "simulated"}, "production": {"data": "equity feed contract", "orders": "equity routes; entitled accounts"}},
        "ca_preferred": {"plain_name": "Canadian preferred share", "symbol": "CA:ENB PR A", "sandbox": {"data": "synthetic income-like behaviour + L1/L2", "orders": "simulated"}, "production": {"data": "equity L1; L2 can be empty for a currently quoted security; terms/fundamentals not supplied", "orders": "equity routes; entitled accounts"}},
        "ca_warrant_right_unit": {"plain_name": "Canadian warrant, right or unit", "symbol": "CA:CAR UN", "sandbox": {"data": "synthetic thin/wide L1/L2", "orders": "simulated"}, "production": {"data": "equity L1; L2 may be shallow or empty; contract terms not supplied", "orders": "equity routes; entitled accounts"}},
        "mx_future": {"plain_name": "Montréal-listed future", "symbol": "MX:CGBU26", "sandbox": {"data": "synthetic L1/L2 and multi-expiry curve", "orders": "simulated"}, "production": {"data": "L1/L2 including implied depth, summaries, RFQ and correction events when emitted", "orders": "entitled derivatives accounts"}},
        "mx_option": {"plain_name": "Montréal-listed equity or index option", "symbol": "MX:AAPL26AUG44.5C21", "sandbox": {"data": "synthetic chain, OI, volume, IV and Greeks", "orders": "simulated"}, "production": {"data": "listed-option L1 when emitted; a zero last is not a trade; analytics source-dependent", "orders": "entitled derivatives accounts"}},
        "mx_future_option": {"plain_name": "Option on a Montréal future", "symbol": "MX:OGB26AUG117.5C17", "sandbox": {"data": "synthetic L1/L2 and future-linked Greeks", "orders": "simulated"}, "production": {"data": "faithful but often unquoted", "orders": "instrument resolution proven; active market required"}},
        "mx_strategy": {"plain_name": "Exchange-listed multi-contract strategy", "symbol": "MX:CRAH27CRAU27", "sandbox": {"data": "synthetic package + related legs", "orders": "simulated"}, "production": {"data": "exchange quote, depth, trades, summaries, reference and status events when emitted", "orders": "2,677 standard forms supported; ratio/custom forms excluded"}},
        "us_equity_etf": {"plain_name": "US share or ETF", "symbol": "US:SPY", "sandbox": {"data": "synthetic L1/L2", "orders": "simulated"}, "production": {"data": "L1; L2 symbol-dependent (SPY proven, AAPL absent upstream)", "orders": "linked US equity accounts"}},
        "us_listed_option": {"plain_name": "US listed option", "symbol": "US:BHYP26OCT50P16", "sandbox": {"data": "synthetic L1/L2 and option metrics", "orders": "simulated"}, "production": {"data": "L1 when emitted; no L2 currently", "orders": "linked US option accounts"}},
        "us_future": {"plain_name": "Selected US future", "symbol": "US:@ESU26", "verified_symbols": ["US:@ESU26", "US:@USU26", "US:@TYU26", "US:@FVU26"], "sandbox": {"data": "synthetic L1/L2 and multi-expiry curve, including fractional Treasury ticks", "orders": "simulated"}, "production": {"data": "selected entitled roots L1/L2", "orders": "enabled families and linked futures accounts"}},
        "tsx_index": {"plain_name": "TSX index value", "symbol": None, "sandbox": {"data": "not modeled", "orders": "not applicable"}, "production": {"data": "unavailable: upstream engine/entitlement not operational", "orders": "not tradeable"}},
        "cash_bond": {"plain_name": "Cash bond", "symbol": None, "sandbox": {"data": "not exposed", "orders": "not exposed"}, "production": {"data": "desktop-modeled only", "orders": "requires a new OTC venue integration"}},
        "forex": {"plain_name": "Foreign exchange", "symbol": None, "sandbox": {"data": "not exposed", "orders": "not exposed"}, "production": {"data": "desktop-modeled only", "orders": "requires a bank or ECN integration"}},
    },
    "markets": {
        "CA": {
            "sandbox": "Synthetic L1/L2 and simulated orders for stock-like listings",
            "instruments": "Canadian equities, ETFs and stock-like listings",
            "market_data": "Official CBBO plus five-level consolidated and deeper venue price views, QJ/TMX order-level TL2 rows, and depth-independent odd-order overlays",
            "orders": "Available across supported lit, dark and smart routes",
            "examples": ["CA:RY", "CA:RY.PT"],
            "limitations": [
                "Only quote messages with cbbo=true are the official consolidated touch",
                "Quote-only states are normal: a preferred or warrant may have L1 while its L2 arrays are empty",
                "bids/asks are rounded Top5; odd_lot_*, special_lot_*, order_bids/order_asks and odd_order_bids/odd_order_asks are additive views and must not be summed into Top5",
                "TSX index values are not currently available",
            ],
        },
        "MX": {
            "sandbox": "Synthetic futures/options/strategies, chains and simulated orders",
            "instruments": "Montréal Exchange futures and listed options",
            "market_data": "Futures L1/L2; listed-option L1",
            "orders": "Futures and listed options available by account entitlement",
            "examples": ["MX:CGBU26", "MX:AAPL26AUG33C21"],
            "limitations": [
                "Some thin or seasonal contracts may have no current quote",
                "Depth can be one level or absent; render the returned shape instead of assuming five levels",
                "Strategy and options-on-futures availability depends on an active market",
            ],
        },
        "US": {
            "sandbox": "Synthetic equities, ETFs, listed options and selected futures; simulated orders",
            "instruments": "US equities/ETFs, listed options and selected futures",
            "market_data": (
                "Equity/ETF L1; symbol-dependent equity/ETF L2; listed-option L1 "
                "when emitted; selected futures L1/L2"
            ),
            "orders": (
                "US equities, listed options and selected futures are available "
                "to credentials linked to the corresponding gateway accounts"
            ),
            "examples": ["US:AAPL", "US:SPY", "US:@ESU26", "US:@USU26", "US:@TYU26", "US:@FVU26"],
            "verified": [
                "US:AAPL L1 and equity order entry",
                "US:SPY L1/L2",
                "US:@ESU26 L1/L2 and futures order entry",
                "US:@USU26, US:@TYU26 and US:@FVU26 Treasury futures L1/L2 and order entry",
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
