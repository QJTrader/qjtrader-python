"""Stable, additive market-event views over QJ's raw wire messages.

The raw stream remains the latency-first contract.  ``normalize_event`` is a
thin client-side view for dashboards, analytics, and AI-built projects that
need consistent names without losing any source fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, MutableMapping, TypedDict


class NormalizedEvent(TypedDict, total=False):
    schema_version: int
    instrument_id: str
    canonical_symbol: str
    asset_class: str
    event_type: str
    exchange_timestamp: str
    publication_timestamp: str
    sequence: int
    venue: str
    source: str
    payload: dict[str, Any]
    inferred_fields: list[str]
    raw: dict[str, Any]


KNOWN_EVENT_TYPES = frozenset({
    "auth_success", "bar", "error", "heartbeat", "level1", "level2",
    "market_event", "quote", "reference", "rtd", "snapshot", "status",
    "subscribed", "subscription_plan", "trade", "trade_correction",
})


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None and value != "":
            return value
    return None


def normalize_timestamp(value: Any) -> str | None:
    """Return an ISO-8601 UTC timestamp when the source shape is recognized.

    QJ sources include ISO timestamps, epoch seconds/milliseconds/nanoseconds,
    and compact exchange values such as ``20260807142626149070``. Unknown
    values stay absent instead of being guessed.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        magnitude = abs(number)
        if magnitude > 1e17:
            number /= 1e9
        elif magnitude > 1e14:
            number /= 1e6
        elif magnitude > 1e11:
            number /= 1e3
        try:
            return datetime.fromtimestamp(number, timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if text.isdigit() and 14 <= len(text) <= 20:
        padded = (text[:14] + text[14:20].ljust(6, "0"))
        try:
            parsed = datetime.strptime(padded, "%Y%m%d%H%M%S%f").replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def infer_aggressor(price: Any, bid: Any, ask: Any) -> str | None:
    """Infer a trade aggressor from a supplied touch, explicitly as inference."""
    try:
        px, bid_px, ask_px = float(price), float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    if px >= ask_px:
        return "buy"
    if px <= bid_px:
        return "sell"
    return None


def normalize_event(message: Mapping[str, Any]) -> NormalizedEvent:
    """Create a stable event envelope while retaining the complete raw message."""
    raw = dict(message)
    data_value = raw.get("data")
    payload: dict[str, Any] = dict(data_value) if isinstance(data_value, Mapping) else {}
    meta_value = raw.get("meta")
    meta: Mapping[str, Any] = meta_value if isinstance(meta_value, Mapping) else {}

    event_type = str(_first(raw, "event_type", "type") or "unknown").lower()
    symbol = _first(raw, "canonical_symbol", "symbol") or _first(payload, "canonical_symbol", "symbol")
    publication = normalize_timestamp(
        _first(raw, "publication_timestamp") or _first(meta, "published_at", "server_publish_ns")
    )
    exchange = normalize_timestamp(
        _first(raw, "exchange_timestamp")
        or _first(payload, "exchange_timestamp", "timestamp", "time", "ts")
    ) or publication

    inferred: list[str] = []
    if event_type == "trade" and not _first(payload, "aggressor", "aggressor_side", "taker_side"):
        aggressor = infer_aggressor(
            _first(payload, "price", "last"),
            _first(payload, "bid", "best_bid"),
            _first(payload, "ask", "best_ask"),
        )
        if aggressor:
            payload["aggressor"] = aggressor
            payload["aggressor_source"] = "inferred_from_supplied_touch"
            inferred.extend(["payload.aggressor", "payload.aggressor_source"])

    event: NormalizedEvent = {
        "schema_version": int(raw.get("schema_version") or meta.get("schema_version") or 1),
        "event_type": event_type,
        "payload": payload,
        "raw": raw,
    }
    optional = {
        "instrument_id": _first(raw, "instrument_id") or _first(payload, "instrument_id"),
        "canonical_symbol": symbol,
        "asset_class": _first(raw, "asset_class") or _first(payload, "asset_class"),
        "exchange_timestamp": exchange,
        "publication_timestamp": publication,
        "sequence": _first(raw, "sequence") or _first(meta, "sequence"),
        "venue": _first(raw, "venue") or _first(payload, "venue") or _first(meta, "venue"),
        "source": _first(raw, "source") or _first(meta, "source"),
    }
    for key, value in optional.items():
        if value is not None and value != "":
            event[key] = value  # type: ignore[literal-required]
    if inferred:
        event["inferred_fields"] = inferred
    return event


@dataclass
class EventDiagnostics:
    """Small counters suitable for a status card or log line."""

    normalized: int = 0
    unknown: int = 0
    rejected: int = 0
    by_type: MutableMapping[str, int] = field(default_factory=dict)

    def observe(self, event: Mapping[str, Any]) -> None:
        event_type = str(event.get("event_type") or "unknown")
        self.normalized += 1
        self.by_type[event_type] = self.by_type.get(event_type, 0) + 1
        if event_type not in KNOWN_EVENT_TYPES:
            self.unknown += 1

    def reject(self) -> None:
        self.rejected += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "normalized": self.normalized,
            "unknown": self.unknown,
            "rejected": self.rejected,
            "by_type": dict(self.by_type),
        }


def normalized_events(messages: Iterable[Mapping[str, Any]], *,
                      diagnostics: EventDiagnostics | None = None) -> Iterator[NormalizedEvent]:
    """Normalize an iterable without dropping unknown event families."""
    for message in messages:
        try:
            event = normalize_event(message)
        except (TypeError, ValueError, OverflowError):
            if diagnostics:
                diagnostics.reject()
            continue
        if diagnostics:
            diagnostics.observe(event)
        yield event
