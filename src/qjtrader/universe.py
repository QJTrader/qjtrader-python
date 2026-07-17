"""Small credential-aware universe helpers built on current QJ truth."""
from __future__ import annotations

import re
from typing import Any

from .availability import market_availability

_MONTH = r"[FGHJKMNQUVXZ]\d{2}"


def product_key(symbol: str) -> str:
    sym = symbol.upper().strip()
    body = sym.split(":", 1)[-1]
    if sym.startswith("CA:"):
        if " PR " in body:
            return "ca_preferred"
        if re.search(r" (WT|RT|UN)(\.|$)", body):
            return "ca_warrant_right_unit"
        return "ca_equity"
    if sym.startswith("US:"):
        if body.startswith("@"):
            return "us_future"
        if re.search(r"\d{2}[A-Z]{3}[\d.]+[CP]\d{1,2}$", body):
            return "us_listed_option"
        return "us_equity_etf"
    if sym.startswith("MX:"):
        if re.search(r"\d{2}[A-Z]{3}[\d.]+[CP]\d{1,2}$", body):
            return "mx_future_option" if body.startswith("OG") else "mx_option"
        if len(re.findall(_MONTH, body)) > 1:
            return "mx_strategy"
        return "mx_future"
    return "unknown"


def describe_instrument(symbol: str, *, data_environment: str | None = None,
                        orders_environment: str | None = None) -> dict[str, Any]:
    """Describe one symbol using the published capability contract."""
    key = product_key(symbol)
    availability = market_availability()
    product = availability["products"].get(key, {})
    order_env = (orders_environment or "unknown").lower()
    return {
        "symbol": symbol,
        "market": symbol.split(":", 1)[0].upper() if ":" in symbol else "unknown",
        "product": key,
        "plain_name": product.get("plain_name", "Unknown or unsupported symbol shape"),
        "data_environment": data_environment or "unknown",
        "orders_environment": orders_environment or "unknown",
        "can_reach_exchange": order_env in {"canary", "live", "real"},
        "sandbox": product.get("sandbox"),
        "production": product.get("production"),
        "availability_reference": availability["reference"],
    }


def search_symbols(symbols: list[str], query: str = "", *, limit: int = 50,
                   data_environment: str | None = None,
                   orders_environment: str | None = None) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    out = []
    for symbol in sorted(set(symbols)):
        desc = describe_instrument(symbol, data_environment=data_environment,
                                   orders_environment=orders_environment)
        haystack = f"{symbol} {desc['product']} {desc['plain_name']}".lower()
        if needle and needle not in haystack:
            continue
        out.append(desc)
        if len(out) >= max(1, min(limit, 200)):
            break
    return out
