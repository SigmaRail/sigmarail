"""Bounded, timestamped evidence emitted by SigmaRail's LEAN loop."""

from __future__ import annotations

import json
from typing import Any


def _safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        return str(value)[:160]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, dict):
        return {str(key)[:64]: _safe(item, depth=depth + 1) for key, item in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [_safe(item, depth=depth + 1) for item in list(value)[:20]]
    return str(value)[:160]


def record_decision(
    algorithm: Any,
    *,
    ticker: str,
    as_of: str,
    stage: str,
    outcome: str,
    reason: str = "",
    rule_id: str | None = None,
    rule_name: str | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append bounded JSON evidence without changing the strategy decision."""
    events = getattr(algorithm, "_strategy_decision_events", None)
    if not isinstance(events, list):
        events = []
        algorithm._strategy_decision_events = events
    sequence = int(getattr(algorithm, "_strategy_decision_sequence", 0)) + 1
    algorithm._strategy_decision_sequence = sequence
    event = {
        "event_id": f"{as_of}:{stage}:{ticker}:{sequence}",
        "ticker": str(ticker).upper()[:24],
        "as_of": str(as_of)[:10],
        "observed_at": str(getattr(algorithm, "Time", ""))[:40],
        "stage": stage,
        "outcome": str(outcome)[:120],
        "reason": str(reason)[:500] if reason else None,
        "rule_id": str(rule_id)[:120] if rule_id else None,
        "rule_name": str(rule_name)[:120] if rule_name else None,
        "inputs": _safe(inputs or {}),
        "outputs": _safe(outputs or {}),
        "strategy_content_hash": getattr(algorithm, "_strategy_content_hash", None),
    }
    event = json.loads(json.dumps(event, separators=(",", ":"), default=str))
    events.append(event)
    if bool(getattr(algorithm, "LiveMode", False)) and len(events) > 500:
        del events[:-500]
    return event
