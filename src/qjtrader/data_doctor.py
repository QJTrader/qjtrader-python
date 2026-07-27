"""Read-only production market-data readiness and timing diagnostics."""
from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Any, Callable, Iterable


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    ordered = sorted(values)

    def value(q: float) -> float:
        index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
        return round(ordered[index], 3)

    return {"p50": value(0.50), "p95": value(0.95), "p99": value(0.99)}


def inspect_stream(stream: Any, symbols: Iterable[str], *,
                   duration: float = 10.0, depth: int = 10,
                   all_venues: bool = False,
                   clock_ns: Callable[[], int] = time.time_ns) -> dict[str, Any]:
    """Inspect one authenticated stream without placing or canceling orders."""
    requested = [str(symbol).strip().upper() for symbol in symbols
                 if str(symbol).strip()]
    if not requested:
        raise ValueError("provide at least one symbol")
    if duration <= 0:
        raise ValueError("duration must be positive")
    if depth < 1:
        raise ValueError("depth must be positive")

    stream.subscribe(
        requested,
        depth=depth,
        venues="all_entitled" if all_venues else None,
    )
    per_symbol: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "messages": 0,
        "types": {},
        "official_cbbo": 0,
        "stale_messages": 0,
        "truncated_messages": 0,
        "venue_state": None,
        "transport_age_ms": [],
        "customer_receive_age_ms": [],
    })
    errors: list[dict[str, Any]] = []
    expanded: list[str] = []
    observed: set[str] = set()

    for message in stream.messages(timeout=duration, include_heartbeats=True):
        now_ns = clock_ns()
        message_type = str(message.get("type") or "unknown")
        if message_type == "subscription_plan":
            expanded = list(map(str, message.get("expanded_symbols") or []))
            continue
        if message_type == "error":
            errors.append({
                "code": message.get("code"),
                "symbol": message.get("symbol"),
                "message": message.get("message") or message.get("error"),
            })
            continue
        symbol = message.get("symbol")
        if not isinstance(symbol, str):
            continue
        observed.add(symbol)
        row = per_symbol[symbol]
        row["messages"] += 1
        row["types"][message_type] = row["types"].get(message_type, 0) + 1
        data = message.get("data") or {}
        meta = message.get("meta") or {}
        if message_type == "quote" and data.get("cbbo") is True:
            row["official_cbbo"] += 1
        if meta.get("stale") is True:
            row["stale_messages"] += 1
        odd_depth = data.get("odd_order_depth") or {}
        if odd_depth.get("bid_truncated") or odd_depth.get("ask_truncated"):
            row["truncated_messages"] += 1
        if message_type == "venue_state":
            row["venue_state"] = {
                "transport_current": data.get("transport_current"),
                "book_initialized": data.get("book_initialized"),
                "book_epoch": data.get("book_epoch"),
            }
        transport_age = meta.get("transport_age_ms")
        if isinstance(transport_age, (int, float)) and transport_age >= 0:
            row["transport_age_ms"].append(float(transport_age))
        published_ns = meta.get("server_publish_ns")
        if isinstance(published_ns, (int, float)) and published_ns > 0:
            receive_age = (now_ns - int(published_ns)) / 1e6
            if receive_age >= 0:
                row["customer_receive_age_ms"].append(receive_age)

    expected = expanded or requested
    missing = sorted(set(expected) - observed)
    stale = sorted(symbol for symbol, row in per_symbol.items()
                   if row["stale_messages"]
                   or (row["venue_state"] is not None and (
                       row["venue_state"]["transport_current"] is not True
                       or row["venue_state"]["book_initialized"] is not True)))
    truncated = sorted(symbol for symbol, row in per_symbol.items()
                       if row["truncated_messages"])
    for row in per_symbol.values():
        row["transport_age_ms"] = _percentiles(row["transport_age_ms"])
        row["customer_receive_age_ms"] = _percentiles(
            row["customer_receive_age_ms"])
    status = ("REJECTED" if errors else "STALE" if stale else
              "INCOMPLETE" if missing or truncated else
              "READY" if observed else "NO_DATA")
    return {
        "status": status,
        "read_only": True,
        "environment": getattr(stream, "environment", None),
        "credential": getattr(stream, "user", None),
        "requested": requested,
        "all_venues": all_venues,
        "expanded_symbols": expanded,
        "observed_symbols": sorted(observed),
        "missing_symbols": missing,
        "stale_symbols": stale,
        "truncated_symbols": truncated,
        "errors": errors,
        "symbols": dict(per_symbol),
        "timing_note": (
            "transport_age_ms is QJ source-to-Gateway age; "
            "customer_receive_age_ms also includes network and local receipt "
            "and assumes synchronized clocks"
        ),
    }
