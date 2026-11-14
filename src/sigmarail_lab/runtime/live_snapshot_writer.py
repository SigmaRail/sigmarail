"""Post live portfolio snapshots to ClickHouse (HTTP JSONEachRow, same pattern as insert_strategy_run)."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from typing import Any


def _ch_env() -> tuple[str, str, str, str]:
    host = (os.environ.get("CLICKHOUSE_HOST") or "").strip()
    port = (os.environ.get("CLICKHOUSE_PORT") or "8123").strip()
    user = (os.environ.get("CLICKHOUSE_USER") or "").strip()
    password = (os.environ.get("CLICKHOUSE_PASSWORD") or "").strip()
    if not host or not user:
        raise RuntimeError("CLICKHOUSE_HOST and CLICKHOUSE_USER required for live snapshot insert")
    return host, port, user, password


def _post_row(table: str, row: dict[str, Any]) -> None:
    host, port, user, password = _ch_env()
    url = f"http://{host}:{port}/?query=INSERT%20INTO%20{table}%20FORMAT%20JSONEachRow"
    payload = (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-ClickHouse-User", user)
    req.add_header("X-ClickHouse-Key", password)
    with urllib.request.urlopen(req, timeout=30) as resp:
        _ = resp.read()


def portfolio_positions_json(algorithm: Any) -> str:
    positions: list[dict[str, Any]] = []
    for kv in algorithm.Portfolio:
        holding = kv.Value
        if not holding.Invested:
            continue
        sym = kv.Key.Value if hasattr(kv.Key, "Value") else str(kv.Key)
        positions.append({
            "symbol": sym,
            "quantity": float(holding.Quantity),
            "market_value": float(holding.HoldingsValue),
            "unrealized_pnl": float(holding.UnrealizedProfit),
        })
    return json.dumps(positions, separators=(",", ":"))


def insert_live_snapshot_from_algorithm(
    algorithm: Any,
    *,
    deployment_id: str,
    as_of: date | None = None,
    source: str = "eod_hook",
    ir_id: str = "",
) -> None:
    """Write one snapshot row from QCAlgorithm portfolio state."""
    deployment_id = (deployment_id or "").strip()
    if not deployment_id:
        algorithm.Debug("live_snapshot: skipped — deployment-id not set")
        return

    session = as_of or algorithm.Time.date()
    equity = float(algorithm.Portfolio.TotalPortfolioValue)
    cash = float(algorithm.Portfolio.Cash)
    positions_json = portfolio_positions_json(algorithm)

    payload = {
        "deployment_id": deployment_id,
        "as_of": session.isoformat(),
        "equity": equity,
        "cash": cash,
        "positions": json.loads(positions_json),
        "source": source,
    }

    row = {
        "deployment_id": deployment_id,
        "as_of": session.isoformat(),
        "equity": equity,
        "cash": cash,
        "buying_power": None,
        "day_pnl": None,
        "total_pnl": None,
        "positions_json": positions_json,
        "source": source,
    }
    _post_row("live_account_snapshots", row)

    if ir_id:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _post_row("strategy_run_artifacts", {
            "run_id": deployment_id,
            "strategy_id": "VeraTradingLab",
            "run_timestamp": ts,
            "artifact_type": "live_snapshot",
            "artifact_json": json.dumps(payload, separators=(",", ":")),
        })

    algorithm.Debug(f"live_snapshot: inserted deployment_id={deployment_id} as_of={session}")
