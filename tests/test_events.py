from qjtrader.events import (EventDiagnostics, infer_aggressor, normalize_event,
                             normalize_timestamp, normalized_events)


def test_compact_exchange_timestamp_and_publication_fallback():
    event = normalize_event({
        "type": "trade",
        "symbol": "MX:CGBU26",
        "data": {"price": 121.42, "size": 5, "time": "20260807142626149070"},
        "meta": {"published_at": "2026-08-07T14:26:26.200000Z", "sequence": 7},
    })
    assert event["event_type"] == "trade"
    assert event["canonical_symbol"] == "MX:CGBU26"
    assert event["exchange_timestamp"] == "2026-08-07T14:26:26.149070Z"
    assert event["publication_timestamp"] == "2026-08-07T14:26:26.200000Z"
    assert event["sequence"] == 7
    assert event["raw"]["data"]["size"] == 5


def test_invalid_exchange_time_falls_back_without_losing_trade():
    event = normalize_event({
        "type": "trade", "symbol": "MX:CRAU26",
        "data": {"price": 97.1, "time": "not-a-time"},
        "meta": {"published_at": "2026-08-07T15:00:00Z"},
    })
    assert event["exchange_timestamp"] == "2026-08-07T15:00:00Z"
    assert event["payload"]["price"] == 97.1


def test_unknown_event_is_visible_and_counted():
    diagnostics = EventDiagnostics()
    events = list(normalized_events([{"type": "future_extension", "data": {"x": 1}}],
                                    diagnostics=diagnostics))
    assert events[0]["event_type"] == "future_extension"
    assert events[0]["payload"] == {"x": 1}
    assert diagnostics.snapshot() == {
        "normalized": 1, "unknown": 1, "rejected": 0,
        "by_type": {"future_extension": 1},
    }


def test_aggressor_is_only_labeled_when_inferred_from_supplied_touch():
    event = normalize_event({
        "type": "trade", "data": {"price": 101, "bid": 100, "ask": 101},
    })
    assert event["payload"]["aggressor"] == "buy"
    assert event["payload"]["aggressor_source"] == "inferred_from_supplied_touch"
    assert "payload.aggressor" in event["inferred_fields"]
    assert infer_aggressor(99, 99, 101) == "sell"


def test_timestamp_helpers_do_not_guess_unknown_values():
    assert normalize_timestamp("n/a") is None
    assert normalize_timestamp(1_786_118_400) == "2026-08-07T16:00:00Z"
