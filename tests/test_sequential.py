from __future__ import annotations

from ir.search.service import SearchService


def _events() -> list[list[dict[str, object]]]:
    return [
        [{"video_id": "v", "ts_ms": 1000, "score": 1.0}],
        [{"video_id": "v", "ts_ms": 3000, "score": 0.9}],
        [{"video_id": "v", "ts_ms": 5000, "score": 0.8}],
    ]


def test_best_chain_orders_events() -> None:
    chain = SearchService._best_chain(_events(), 500, 4000, 0.0, 60000)
    assert chain is not None
    assert chain["video_id"] == "v"
    assert [event["ts_ms"] for event in chain["events"]] == [1000, 3000, 5000]


def test_best_chain_rejects_gap_over_limit() -> None:
    events = _events()
    events[2][0]["ts_ms"] = 20000
    assert SearchService._best_chain(events, 500, 4000, 0.0, 60000) is None


def test_best_chain_rejects_span_over_limit() -> None:
    assert SearchService._best_chain(_events(), 500, 60000, 0.0, 3000) is None


def test_best_chain_applies_gap_penalty() -> None:
    loose = _events()
    loose[2][0]["ts_ms"] = 3800
    free = SearchService._best_chain(_events(), 500, 4000, 0.0, 60000)
    penalized = SearchService._best_chain(loose, 500, 4000, 0.5, 60000)
    assert free is not None and penalized is not None
    assert float(free["score"]) > float(penalized["score"])


def test_best_window_keeps_events_within_span() -> None:
    events = _events()
    chain = SearchService._best_window(events, 60000)
    assert chain is not None
    assert [event["ts_ms"] for event in chain["events"]] == [1000, 3000, 5000]


def test_best_window_drops_far_events() -> None:
    events = _events()
    events[2][0]["ts_ms"] = 90000
    assert SearchService._best_window(events, 60000) is None
