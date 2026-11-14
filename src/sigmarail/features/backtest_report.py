"""Agent-oriented backtest run digests (strategy_runs + artifacts)."""

from __future__ import annotations

from .accounting import reconcile_accounting
from .artifact_redaction import safe_artifact_output, sanitize_artifact

import json
import hashlib
import time
from typing import Any


def benchmark_metrics(
    artifact: Any,
    period_start: Any = None,
    period_end: Any = None,
    portfolio_return: Any = None,
) -> dict[str, Any]:
    """Validate benchmark evidence against the actual LEAN session dates.

    The sidecar is generated from ``daily_metrics.closeadj`` and merged into the
    immutable ``backtest_results`` artifact by the run recorder. Relative return
    is arithmetic excess return over the same run interval, and is only emitted
    when the adjusted series and LEAN benchmark chart both align to the portfolio
    equity chart.
    """
    import math
    from datetime import date, datetime, timezone

    result = {"status": "unavailable", "reason": "missing_series", "ticker": None,
              "price_basis": None, "source": None, "observation_count": 0,
              "relative_return": None, "benchmark_return": None}

    def chart_points(chart_name: str, series_name: str) -> list[tuple[date, float]]:
        try:
            raw = artifact["charts"][chart_name]["series"][series_name]["values"]
        except (KeyError, TypeError):
            return []
        points: list[tuple[date, float]] = []
        for row in raw if isinstance(raw, list) else []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                day = datetime.fromtimestamp(float(row[0]), tz=timezone.utc).date()
                value = float(row[1])
            except (TypeError, ValueError, OverflowError, OSError):
                continue
            if math.isfinite(value):
                points.append((day, value))
        return points

    try:
        series = artifact.get("benchmarkSeries")
        if not isinstance(series, dict):
            old_chart = chart_points("Benchmark", "Benchmark")
            if old_chart and all(value <= 0 for _, value in old_chart):
                result["reason"] = "invalid_price"
            return result
        ticker = series.get("ticker")
        basis = series.get("price_basis")
        source = series.get("source")
        observations = series.get("observations")
        result.update(ticker=ticker if isinstance(ticker, str) else None,
                      price_basis=basis if isinstance(basis, str) else None,
                      source=source if isinstance(source, str) else None)
        if not isinstance(ticker, str) or not ticker.strip():
            result["reason"] = "invalid_series"
            return result
        # Cash is an explicit constant benchmark, not a missing market-data
        # series. Its zero return is valid only when LEAN emitted aligned
        # portfolio and benchmark chart sessions.
        if ticker.upper() == "CASH":
            if basis != "cash_zero_return" or source != "constant_cash":
                result["reason"] = "invalid_price_basis"
                return result
            portfolio_points = chart_points("Strategy Equity", "Return")
            benchmark_points = chart_points("Benchmark", "Benchmark")
            start = date.fromisoformat(str(period_start)[:10]) if period_start else None
            end = date.fromisoformat(str(period_end)[:10]) if period_end else None
            if start is None or end is None or end < start:
                result["reason"] = "missing_period"
                return result
            expected_days = {day for day, _ in portfolio_points if start <= day <= end}
            chart_days = {day for day, _ in benchmark_points if start <= day <= end}
            if not expected_days or chart_days != expected_days:
                result["reason"] = "unaligned_or_duplicate_dates"
                return result
            try:
                strategy_return = float(portfolio_return)
                if not math.isfinite(strategy_return):
                    strategy_return = None
            except (TypeError, ValueError, OverflowError):
                strategy_return = None
            result.update(status="available", reason=None, observation_count=len(expected_days),
                          benchmark_return=0.0,
                          relative_return=strategy_return)
            return result
        if basis != "adjusted_total_return" or source != "daily_metrics.closeadj":
            result["reason"] = "invalid_price_basis"
            return result
        if not isinstance(observations, list) or len(observations) < 2:
            result["reason"] = "short_series"
            return result
        parsed = []
        for item in observations:
            if not isinstance(item, dict):
                result["reason"] = "invalid_observation"
                return result
            day = date.fromisoformat(str(item["date"])[:10])
            close = float(item["close"])
            if not math.isfinite(close) or close <= 0:
                result["reason"] = "invalid_price"
                return result
            parsed.append((day, close))
        if any(a[0] >= b[0] for a, b in zip(parsed, parsed[1:])):
            result["reason"] = "unaligned_or_duplicate_dates"
            return result
        if not period_start or not period_end:
            result["reason"] = "missing_period"
            return result
        start = date.fromisoformat(str(period_start)[:10])
        end = date.fromisoformat(str(period_end)[:10])
        if end < start:
            result["reason"] = "invalid_period"
            return result
        market_sessions = series.get("market_session_dates")
        if not isinstance(market_sessions, list) or not market_sessions:
            result["reason"] = "missing_market_observations"
            return result
        try:
            parsed_sessions = [date.fromisoformat(str(day)[:10]) for day in market_sessions]
        except (TypeError, ValueError):
            result["reason"] = "invalid_market_observations"
            return result
        if len(set(parsed_sessions)) != len(parsed_sessions):
            result["reason"] = "invalid_market_observations"
            return result
        source_days = {day for day, _ in parsed}
        in_period_sessions = {day for day in parsed_sessions if start <= day <= end}
        if not in_period_sessions:
            result["reason"] = "missing_market_observations"
            return result
        if not in_period_sessions.issubset(source_days):
            result["reason"] = "missing_market_observation"
            return result
        in_period = [(day, close) for day, close in parsed if start <= day <= end]
        if len(in_period) < 2:
            result["reason"] = "short_series"
            return result
        portfolio_points = chart_points("Strategy Equity", "Return")
        benchmark_points = chart_points("Benchmark", "Benchmark")
        expected_days = {day for day, _ in portfolio_points if start <= day <= end}
        actual_days = {day for day, _ in in_period}
        if not expected_days or actual_days != expected_days:
            result["reason"] = "stale_series" if expected_days and max(actual_days) < max(expected_days) else "short_series"
            return result
        chart_days = {day for day, _ in benchmark_points if start <= day <= end}
        if chart_days != expected_days:
            result["reason"] = "stale_series" if expected_days and chart_days < expected_days else "short_series"
            return result
        prices_by_day = dict(in_period)
        if any(
            not math.isclose(chart_price, prices_by_day[day], rel_tol=1e-9, abs_tol=1e-8)
            for day, chart_price in benchmark_points
            if start <= day <= end and day in prices_by_day
        ):
            result["reason"] = "benchmark_chart_mismatch"
            return result
        if any(value <= 0 for day, value in benchmark_points if day in expected_days):
            result["reason"] = "invalid_price"
            return result
        benchmark_return = in_period[-1][1] / in_period[0][1] - 1.0
        try:
            strategy_return = float(portfolio_return)
            if not math.isfinite(strategy_return):
                strategy_return = None
        except (TypeError, ValueError, OverflowError):
            strategy_return = None
        result.update(status="available", reason=None, observation_count=len(in_period),
                      benchmark_return=benchmark_return,
                      relative_return=(strategy_return - benchmark_return
                                       if strategy_return is not None else None))
        return result
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        result["reason"] = "invalid_series"
        return result

def closed_trade_metrics(artifact: Any) -> dict[str, Any]:
    """Derive gross metrics only from complete LEAN totalPerformance evidence.

    profitLoss is gross realized P&L; fees are reported separately, never deducted.
    No raw evidence or evidence-controlled text is returned.
    """
    import math

    result = {"profit_factor": None, "status": "unavailable",
              "source": "unavailable", "closed_record_win_rate": None,
              "closed_record_count": None, "gross_profit": None, "gross_loss": None,
              "pnl_basis": "gross_before_fees"}

    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError
        value = float(value)
        if not math.isfinite(value):
            raise ValueError
        return value

    try:
        performance = artifact["totalPerformance"]
        stats = performance["tradeStatistics"]
        count = number(stats["totalNumberOfTrades"])
        if count <= 0 or not count.is_integer():
            return result
        trades = performance.get("closedTrades")
        if "closedTrades" in performance:
            if not isinstance(trades, list) or len(trades) != count:
                return result
            outcomes = [number(trade["profitLoss"]) for trade in trades]
            profit = math.fsum(v for v in outcomes if v > 0)
            loss = -math.fsum(v for v in outcomes if v < 0)
            result["closed_record_win_rate"] = sum(v > 0 for v in outcomes) / count
            source = "totalPerformance.closedTrades"
        else:
            profit = number(stats["totalProfit"])
            loss = -number(stats["totalLoss"])
            source = "totalPerformance.tradeStatistics"
        if profit < 0 or loss < 0:
            return result
        result.update(source=source, closed_record_count=int(count),
                      gross_profit=profit, gross_loss=loss)
        if profit == loss == 0:
            return result
        if loss == 0:
            result["status"] = "infinite"
        else:
            ratio = profit / loss
            if math.isfinite(ratio):
                result.update(profit_factor=ratio, status="available")
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return result


def _row_dict(columns: list[str], row: tuple) -> dict[str, Any]:
    return dict(zip(columns, row))


def _parse_summary_stats(summary_json: str) -> dict[str, Any]:
    try:
        summary = sanitize_artifact(json.loads(summary_json))
        if not isinstance(summary, dict):
            return {}
    except (json.JSONDecodeError, TypeError):
        return {}
    stats = summary.get("statistics") or {}
    if not isinstance(stats, dict):
        return {}
    return stats


def _metric_highlights(run: dict[str, Any], stats: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    tr = run.get("total_return")
    if tr is not None:
        highlights.append(f"Total return: {float(tr):.2%}")
    sharpe = run.get("sharpe_ratio")
    if sharpe is not None:
        highlights.append(f"Sharpe: {float(sharpe):.2f}")
    dd = run.get("max_drawdown")
    if dd is not None:
        highlights.append(f"Max drawdown: {float(dd):.2%}")
    if stats.get("Total Orders"):
        highlights.append(f"Orders: {stats.get('Total Orders')}")
    if run.get("ir_id"):
        highlights.append(f"Model ir_id: {run['ir_id']}")
    return highlights


def _validity_warnings(
    run: dict[str, Any], artifact_types: list[str], benchmark: dict[str, Any],
    accounting: dict[str, Any], lineage: dict[str, Any],
) -> list[dict[str, str]]:
    """Return fixed, actionable warnings for unresolved validity dimensions."""
    warnings: list[dict[str, str]] = []

    def add(code: str, message: str, action: str) -> None:
        warnings.append({"code": code, "message": message, "action": action})

    add("quality_unverified", "Backtest quality has not been certified.",
        "Review applicable data-quality and point-in-time evidence; keep this run exploratory until an authorized certification exists.")
    if accounting.get("status") != "reconciled":
        add("accounting_unreconciled", "Accounting evidence is incomplete or does not reconcile.",
            "Review accounting_reconciliation.missing_artifacts and unresolved_reasons; complete the accounting evidence contract and reconcile it.")
    if benchmark.get("status") != "available":
        add("benchmark_invalid_or_unavailable", "Benchmark-relative metrics are unavailable.",
            "Review metric_metadata.benchmark.reason and provide valid, aligned benchmark evidence for the run period.")
    if lineage.get("exact_reproduction_available") is not True:
        add("historical_snapshot_incomplete", "Historical strategy or data-version evidence is incomplete.",
            "Review provenance.strategy_lineage.missing_evidence and preserve a verified run-bound snapshot with frozen data versions.")
    return warnings


def _warnings(run: dict[str, Any], artifact_types: list[str], benchmark: dict[str, Any] | None = None) -> list[str]:
    warnings: list[str] = []
    if run.get("git_commit") in ("local", "", None):
        warnings.append("git_commit is local — MCP path did not record repo SHA")
    total_orders = run.get("total_orders")
    if total_orders == 0:
        warnings.append(
            "total_orders is 0 — empty universe or no fills; verify SIGMARAIL_API_URL "
            "and vera_query_service logs"
        )
    if not run.get("ir_content_hash"):
        warnings.append("ir_content_hash missing — lineage weaker than CI runs")
    if "summary" not in artifact_types:
        warnings.append("No summary artifact — metrics may be incomplete")
    if run.get("trigger") == "mcp" and not run.get("ir_schema_version"):
        warnings.append("ir_schema_version not set on MCP insert path")
    return warnings


def _accounting_summary(ledger: Any = None, order_events: Any = None) -> dict[str, Any]:
    """Summarize captured LEAN accounting evidence without claiming reconciliation."""
    from collections import defaultdict
    from decimal import Decimal, InvalidOperation

    ledger = ledger if isinstance(ledger, dict) else {}
    fills = ledger.get("fills") if isinstance(ledger.get("fills"), list) else []
    if not fills and isinstance(order_events, list):
        for event in order_events:
            if not isinstance(event, dict):
                continue
            try:
                if Decimal(str(event.get("fillQuantity") or 0)) == 0:
                    continue
            except (InvalidOperation, ValueError):
                continue
            fills.append(
                {
                    "fee_amount": event.get("orderFeeAmount"),
                    "fee_currency": event.get("orderFeeCurrency"),
                    "fill_quantity": event.get("fillQuantity"),
                }
            )

    fee_totals: dict[str, Decimal] = defaultdict(Decimal)
    signed_fill_cashflows = Decimal(0)
    fills_with_fee = 0
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        try:
            quantity = Decimal(str(fill.get("fill_quantity") or 0))
            price = Decimal(str(fill.get("fill_price") or 0))
        except (InvalidOperation, ValueError):
            quantity = price = Decimal(0)
        signed_fill_cashflows -= quantity * price
        if fill.get("fee_amount") is not None:
            try:
                amount = Decimal(str(fill["fee_amount"]))
            except (InvalidOperation, ValueError):
                continue
            currency = str(fill.get("fee_currency") or "unknown")
            fee_totals[currency] += amount
            fills_with_fee += 1

    snapshots = ledger.get("daily_snapshots") if isinstance(ledger.get("daily_snapshots"), list) else []
    initial = ledger.get("initial") if isinstance(ledger.get("initial"), dict) else {}
    final = ledger.get("final") if isinstance(ledger.get("final"), dict) else {}
    holdings_marks = sum(
        1
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        for holding in (snapshot.get("holdings") or [])
        if isinstance(holding, dict) and holding.get("price") is not None
    )
    final_holdings = final.get("holdings") if isinstance(final.get("holdings"), list) else []
    final_holdings_mark_count = sum(
        1 for holding in final_holdings
        if isinstance(holding, dict) and holding.get("price") is not None
    )
    actions = ledger.get("corporate_actions") if isinstance(ledger.get("corporate_actions"), list) else []
    orders = ledger.get("orders") if isinstance(ledger.get("orders"), list) else []
    missing = []
    if not orders and isinstance(order_events, list):
        # LEAN's order-event artifact includes submitted/canceled as well as
        # filled events. Reconstruct only stable order identity fields, and
        # reject conflicting duplicates instead of guessing.
        by_id: dict[str, dict[str, str]] = {}
        conflicting_order_ids: set[str] = set()
        for event in order_events:
            if not isinstance(event, dict) or event.get("orderId") is None:
                continue
            order_id = str(event["orderId"])
            row = {
                "id": order_id,
                "symbol": str(event.get("symbolValue") or event.get("symbol") or ""),
                "quantity": str(event.get("quantity") or "0"),
            }
            if order_id in by_id and by_id[order_id] != row:
                conflicting_order_ids.add(order_id)
            by_id[order_id] = row
        orders = [row for key, row in sorted(by_id.items()) if key not in conflicting_order_ids]
        if conflicting_order_ids:
            missing.append("consistent submitted-order identity for order IDs " + ",".join(sorted(conflicting_order_ids)))
    action_counts: dict[str, int] = defaultdict(int)
    for action in actions:
        if isinstance(action, dict):
            action_counts[str(action.get("kind") or "unknown")] += 1

    if not ledger:
        missing.append("accounting_ledger artifact is absent")
    if initial.get("cash") is None:
        missing.append("initial cash balance")
    if final.get("cash") is None:
        missing.append("final cash balance")
    if not snapshots:
        missing.append("daily cash and position-mark snapshots")
    if not orders:
        missing.append("complete submitted-order records")
    if final_holdings and final_holdings_mark_count != len(final_holdings):
        missing.append("terminal mark for one or more open holdings")
    if fills and fills_with_fee != len(fills):
        missing.append("fee amount or currency on one or more fills")
    if ledger and ledger.get("corporate_action_slices_seen", 0) <= 0:
        missing.append("evidence that corporate-action slices were observed")

    initial_cash = initial.get("cash")
    final_cash = final.get("cash")
    cash_bridge = None
    if initial_cash is not None and final_cash is not None and len(fills) == fills_with_fee:
        try:
            fees = sum(fee_totals.values(), Decimal(0))
            cash_bridge = {
                "signed_fill_cashflows": str(signed_fill_cashflows),
                "fees": str(fees),
                "expected_final_cash": str(Decimal(str(initial_cash)) + signed_fill_cashflows - fees),
                "observed_final_cash": str(Decimal(str(final_cash))),
                "residual": str(Decimal(str(final_cash)) - (Decimal(str(initial_cash)) + signed_fill_cashflows - fees)),
            }
        except (InvalidOperation, ValueError):
            cash_bridge = None

    final_marked_value = None
    final_equity_residual = None
    try:
        if final_holdings and final_holdings_mark_count == len(final_holdings):
            final_marked_value = sum(Decimal(str(h["value"])) for h in final_holdings)
            final_equity_residual = Decimal(str(final.get("equity"))) - (Decimal(str(final_cash)) + final_marked_value)
    except (InvalidOperation, ValueError, KeyError, TypeError):
        final_marked_value = final_equity_residual = None

    unsupported_positions = []
    for holding in final_holdings:
        try:
            if Decimal(str(holding.get("quantity") or 0)) < 0:
                unsupported_positions.append(str(holding.get("ticker") or "unknown"))
        except (InvalidOperation, ValueError):
            unsupported_positions.append(str(holding.get("ticker") or "unknown"))

    return {
        "evidence_status": "evidence_available" if ledger else ("partial" if fills else "unavailable"),
        "reconciliation_status": "not_evaluated",
        "account_currency": ledger.get("account_currency"),
        "initial_cash": initial.get("cash"),
        "initial_equity": initial.get("equity"),
        "final_cash": final.get("cash"),
        "final_equity": final.get("equity"),
        "fill_count": len(fills),
        "fills_with_fee": fills_with_fee,
        "fees_by_currency": {currency: str(total) for currency, total in sorted(fee_totals.items())},
        "daily_snapshot_count": len(snapshots),
        "holdings_mark_count": holdings_marks,
        "final_holdings_count": len(final_holdings),
        "final_holdings_mark_count": final_holdings_mark_count,
        "order_count": len(orders),
        "orders_with_fill_events": len({str(fill.get("order_id")) for fill in fills if isinstance(fill, dict) and fill.get("order_id") is not None}),
        "cash_bridge": cash_bridge,
        "final_marked_holdings_value": str(final_marked_value) if final_marked_value is not None else None,
        "final_equity_residual": str(final_equity_residual) if final_equity_residual is not None else None,
        "unsupported_short_positions": unsupported_positions,
        "corporate_action_count": len(actions),
        "corporate_actions_by_kind": dict(sorted(action_counts.items())),
        "missing_evidence": missing,
        "interpretation": "Cash bridge and terminal marks are direct arithmetic checks on captured artifacts. Full C-ACCOUNTING-V1 reconciliation remains separate and may be unsupported (for example, short positions).",
    }


def _read_accounting_artifacts(client: Any, run_id: str, artifact_types: list[str]) -> tuple[Any, Any]:
    payloads: dict[str, Any] = {}
    for artifact_type in ("accounting_ledger", "order_events"):
        if artifact_type not in artifact_types:
            continue
        rows = client.query(
            "SELECT artifact_json FROM strategy_run_artifacts FINAL"
            " WHERE run_id = %(run_id)s AND artifact_type = %(artifact_type)s LIMIT 1",
            parameters={"run_id": run_id, "artifact_type": artifact_type},
        )
        if not rows.result_rows:
            continue
        try:
            payloads[artifact_type] = json.loads(rows.result_rows[0][0])
        except (ValueError, TypeError, RecursionError):
            payloads[artifact_type] = None
    return payloads.get("accounting_ledger"), payloads.get("order_events")


def _strategy_lineage(client: Any, run_id: str, ir_content_hash: Any) -> dict[str, Any]:
    """Resolve only a run-bound snapshot; never substitute today's mutable spec."""
    rows = client.query(
        "SELECT artifact_json FROM strategy_run_artifacts FINAL"
        " WHERE run_id = %(run_id)s AND artifact_type = 'strategy_lineage' LIMIT 1",
        parameters={"run_id": run_id},
    )
    if not rows.result_rows:
        return {
            "snapshot_status": "unavailable",
            "content_hash": str(ir_content_hash or "").strip() or None,
            "missing_evidence": [
                "strategy_lineage_artifact_missing",
                "run_bound_snapshot_bytes_missing",
                "authored_evaluation_window_missing",
                "effective_runtime_override_sources_missing",
                "data_provider_window_missing",
                "frozen_data_versions",
            ],
            "exact_reproduction_available": False,
        }
    try:
        record = json.loads(rows.result_rows[0][0])
    except (ValueError, TypeError, RecursionError):
        return {
            "snapshot_status": "unavailable",
            "missing_evidence": ["strategy_lineage_artifact_invalid_json"],
            "exact_reproduction_available": False,
        }
    if not isinstance(record, dict):
        return {
            "snapshot_status": "unavailable",
            "missing_evidence": ["strategy_lineage_artifact_invalid_shape"],
            "exact_reproduction_available": False,
        }
    snapshot = record.get("snapshot_json")
    expected = str(ir_content_hash or "").strip()
    record_missing = record.get("missing_evidence", [])
    if not isinstance(record_missing, list) or not all(isinstance(item, str) for item in record_missing):
        return {
            "snapshot_status": "unavailable",
            "missing_evidence": ["strategy_lineage_artifact_invalid_shape"],
            "exact_reproduction_available": False,
        }
    if snapshot is not None:
        actual = hashlib.sha256(str(snapshot).encode("utf-8")).hexdigest()
        if record.get("hash_algorithm") != "sha256" or record.get("hash_input") != "exact_utf8_json_bytes":
            status = "unavailable"
            missing = ["unsupported_snapshot_hash_contract"]
        elif not expected:
            status = "unavailable"
            missing = ["run_ir_content_hash_missing"]
        elif actual != expected or record.get("expected_content_hash") != expected:
            status = "hash_mismatch"
            missing = ["snapshot_hash_does_not_match_run"]
        else:
            status = "verified"
            missing = list(record_missing)
    else:
        status = str(record.get("snapshot_status") or "unavailable")
        missing = list(record_missing) or ["run_bound_ir_snapshot_missing"]
        # A producer cannot assert verification without supplying bytes that we
        # independently hash against strategy_runs.ir_content_hash.
        if status == "verified":
            status = "unavailable"
            missing = ["run_bound_ir_snapshot_missing"]
    if status != "verified":
        missing = missing if isinstance(missing, list) and all(isinstance(item, str) for item in missing) else ["strategy_lineage_artifact_invalid_shape"]
    data_versions = record.get("data_versions", {"status": "unavailable", "missing": ["frozen_data_versions"]})
    if not isinstance(data_versions, dict):
        data_versions = {"status": "unavailable", "missing": ["data_versions_evidence_invalid"]}
    data_missing = data_versions.get("missing", [])
    if not isinstance(data_missing, list) or not all(isinstance(item, str) for item in data_missing):
        data_missing = ["data_versions_evidence_invalid"]
    missing = list(dict.fromkeys(missing + data_missing))
    if data_versions.get("status") != "available" and not data_missing:
        missing.append("frozen_data_versions_unavailable")
    return {
        "snapshot_status": status,
        "ir_id": record.get("ir_id"),
        "content_hash": expected or None,
        "snapshot": snapshot if status == "verified" else None,
        "hash_algorithm": record.get("hash_algorithm"),
        "hash_input": record.get("hash_input"),
        "authored_window": record.get("authored_window") if status == "verified" else None,
        "effective_window": record.get("effective_window") if status == "verified" else None,
        "data_provider_window": record.get("data_provider_window") if status == "verified" else None,
        "missing_evidence": missing,
        "data_versions": data_versions,
        "exact_reproduction_available": status == "verified" and not missing and data_versions.get("status") == "available",
    }


@safe_artifact_output
def get_backtest_report(client: Any, run_id: str) -> dict[str, Any]:
    """Build LLM-friendly digest for one backtest run."""
    run_id = (run_id or "").strip()
    if not run_id:
        return {"error": "run_id is required", "code": "invalid_argument"}

    run_rows = client.query(
        "SELECT run_id, strategy_id, run_timestamp, period_start, period_end,"
        "       ir_id, ir_schema_version, ir_content_hash, run_type, trigger,"
        "       total_return, annual_return, sharpe_ratio, sortino_ratio, max_drawdown,"
        "       win_rate, profit_factor, total_orders, total_fees, start_equity, end_equity,"
        "       trimRight(CAST(git_commit AS Nullable(String)), '\\0') AS git_commit, git_branch, image"
        " FROM strategy_runs FINAL WHERE run_id = %(run_id)s LIMIT 1",
        parameters={"run_id": run_id},
    )
    if not run_rows.result_rows:
        return {"error": f"run not found: {run_id}", "code": "not_found"}

    run = _row_dict(run_rows.column_names, run_rows.result_rows[0])
    lineage = _strategy_lineage(client, run_id, run.get("ir_content_hash"))

    artifact_rows = client.query(
        "SELECT artifact_type, length(artifact_json) AS json_bytes"
        " FROM strategy_run_artifacts FINAL WHERE run_id = %(run_id)s",
        parameters={"run_id": run_id},
    )
    artifact_types = [r[0] for r in artifact_rows.result_rows]
    artifact_refs = [
        {"artifact_type": _row_dict(artifact_rows.column_names, r)["artifact_type"],
         "json_bytes": _row_dict(artifact_rows.column_names, r).get("json_bytes")}
        for r in artifact_rows.result_rows
    ]

    summary_stats: dict[str, Any] = {}
    if "summary" in artifact_types:
        sum_rows = client.query(
            "SELECT artifact_json FROM strategy_run_artifacts FINAL"
            " WHERE run_id = %(run_id)s AND artifact_type = 'summary' LIMIT 1",
            parameters={"run_id": run_id},
        )
        if sum_rows.result_rows:
            summary_stats = _parse_summary_stats(sum_rows.result_rows[0][0])

    evidence = None
    if "backtest_results" in artifact_types:
        evidence_rows = client.query(
            "SELECT artifact_json FROM strategy_run_artifacts FINAL"
            " WHERE run_id = %(run_id)s AND artifact_type = 'backtest_results' LIMIT 1",
            parameters={"run_id": run_id},
        )
        if evidence_rows.result_rows:
            try:
                evidence = sanitize_artifact(json.loads(evidence_rows.result_rows[0][0], parse_float=str))
            except (ValueError, TypeError, RecursionError):
                pass
    derived = closed_trade_metrics(evidence)
    benchmark = benchmark_metrics(
        evidence,
        run.get("period_start"),
        run.get("period_end"),
        run.get("total_return"),
    )
    accounting_ledger, order_events = _read_accounting_artifacts(client, run_id, artifact_types)
    try:
        average_ratio = float(summary_stats.get("Profit-Loss Ratio"))
        import math
        if not math.isfinite(average_ratio):
            average_ratio = None
    except (ValueError, TypeError, OverflowError):
        average_ratio = None

    metrics = {
        "total_return": run.get("total_return"),
        "annual_return": run.get("annual_return"),
        "sharpe_ratio": run.get("sharpe_ratio"),
        "sortino_ratio": run.get("sortino_ratio"),
        "max_drawdown": run.get("max_drawdown"),
        "win_rate": run.get("win_rate"),
        "profit_factor": derived["profit_factor"],
        "average_win_loss_ratio": average_ratio,
        "closed_record_win_rate": derived["closed_record_win_rate"],
        "total_orders": run.get("total_orders"),
        "total_fees": run.get("total_fees"),
        "start_equity": run.get("start_equity"),
        "end_equity": run.get("end_equity"),
        "benchmark_return": benchmark["benchmark_return"],
        "relative_return": benchmark["relative_return"],
        "spy_return": (benchmark["benchmark_return"] if benchmark["ticker"] == "SPY" else None),
        "alpha": run.get("alpha") if benchmark["status"] == "available" else None,
        "beta": run.get("beta") if benchmark["status"] == "available" else None,
        "information_ratio": run.get("information_ratio") if benchmark["status"] == "available" else None,
    }
    validity_warnings = _validity_warnings(
        run, artifact_types, benchmark,
        reconcile_accounting(evidence), lineage,
    )

    return {
        "run_id": run_id,
        "quality_status": "pending_unverified",
        "data_quality_run_id": None,
        "ir_id": run.get("ir_id"),
        "period": {
            "start": str(run.get("period_start") or ""),
            "end": str(run.get("period_end") or ""),
        },
        "run_type": run.get("run_type"),
        "trigger": run.get("trigger"),
        "run_timestamp": str(run.get("run_timestamp") or ""),
        "metrics": metrics,
        "accounting_reconciliation": reconcile_accounting(evidence),
        "metric_metadata": {
            "profit_factor": derived,
            "win_rate": {"population": "LEAN portfolio statistics", "source": "strategy_runs.win_rate",
                         "pnl_basis": "LEAN portfolio outcome classification; fees separate"},
            "closed_record_win_rate": {"population": "all closed records including zero P&L",
                                       "pnl_basis": "gross_before_fees", "source": derived["source"]},
            "average_win_loss_ratio": {"source": "summary.statistics.Profit-Loss Ratio",
                                       "definition": "LEAN average win / absolute average loss; not profit factor"},
            "total_fees": {"definition": "separate fee amount; not deducted from gross trade P&L"},
            "total_return": {"definition": "LEAN portfolio net return"},
            "benchmark": benchmark,
            "relative_return": {"definition": "same-period arithmetic excess return: portfolio total return minus adjusted benchmark return",
                                "status": benchmark["status"]},
        },
        "summary_statistics_keys": sorted(summary_stats.keys()) if summary_stats else [],
        "highlights": _metric_highlights(run, summary_stats),
        "warnings": _warnings(run, artifact_types, benchmark)
                    + [warning["message"] for warning in validity_warnings],
        "validity_warnings": validity_warnings,
        "artifact_refs": artifact_refs,
        "accounting_evidence": _accounting_summary(accounting_ledger, order_events),
        "provenance": {
            "git_commit": run.get("git_commit"),
            "git_branch": run.get("git_branch"),
            "image": run.get("image"),
            "ir_schema_version": run.get("ir_schema_version"),
            "ir_content_hash": run.get("ir_content_hash"),
            "strategy_lineage": lineage,
        },
    }


@safe_artifact_output
def get_backtest_accounting(client: Any, run_id: str) -> dict[str, Any]:
    """Return compact accounting-evidence coverage for one run; never plug residuals."""
    run_id = (run_id or "").strip()
    if not run_id:
        return {"error": "run_id is required", "code": "invalid_argument"}
    rows = client.query(
        "SELECT artifact_type FROM strategy_run_artifacts FINAL"
        " WHERE run_id = %(run_id)s",
        parameters={"run_id": run_id},
    )
    artifact_types = [str(row[0]) for row in rows.result_rows]
    ledger, events = _read_accounting_artifacts(client, run_id, artifact_types)
    return {
        "run_id": run_id,
        "accounting_evidence": _accounting_summary(ledger, events),
        "artifact_refs": [
            artifact_type for artifact_type in ("accounting_ledger", "order_events")
            if artifact_type in artifact_types
        ],
    }


@safe_artifact_output
def list_runs_by_ir_id(client: Any, ir_id: str, limit: int = 20) -> dict[str, Any]:
    ir_id = (ir_id or "").strip()
    if not ir_id:
        return {"error": "ir_id is required", "code": "invalid_argument"}
    limit = max(1, min(int(limit), 200))
    rows = client.query(
        "SELECT run_id, strategy_id, run_timestamp, period_start, period_end,"
        "       ir_id, run_type, trigger, total_return, annual_return, sharpe_ratio,"
        "       max_drawdown, trimRight(CAST(git_commit AS Nullable(String)), '\\0') AS git_commit"
        " FROM strategy_runs FINAL"
        " WHERE ir_id = %(ir_id)s"
        " ORDER BY run_timestamp DESC"
        f" LIMIT {limit}",
        parameters={"ir_id": ir_id},
    )
    return {
        "ir_id": ir_id,
        "runs": [_row_dict(rows.column_names, r) for r in rows.result_rows],
    }


@safe_artifact_output
def wait_for_backtest(
    client: Any,
    job_id: str,
    timeout_sec: int = 3600,
    poll_interval_sec: float = 5.0,
) -> dict[str, Any]:
    """Poll backtest_jobs until done/failed or timeout; return job row + report on success."""
    job_id = (job_id or "").strip()
    if not job_id:
        return {"error": "job_id is required", "code": "invalid_argument"}
    timeout_sec = max(10, min(int(timeout_sec), 86400))
    poll_interval_sec = max(1.0, min(float(poll_interval_sec), 60.0))

    deadline = time.monotonic() + timeout_sec
    last_status = None

    while time.monotonic() < deadline:
        rows = client.query(
            "SELECT job_id, ir_id, start_date, end_date, status, runner_id,"
            "       submitted_at, started_at, completed_at, error_message, lean_output_path"
            " FROM backtest_jobs FINAL WHERE job_id = %(job_id)s LIMIT 1",
            parameters={"job_id": job_id},
        )
        if not rows.result_rows:
            return {"error": f"job not found: {job_id}", "code": "not_found"}

        job = sanitize_artifact(_row_dict(rows.column_names, rows.result_rows[0]))
        status = job.get("status")
        last_status = status

        if status == "done":
            report = get_backtest_report(client, job_id)
            return {
                "job": job,
                "status": "done",
                "report": report,
            }
        if status == "failed":
            return {
                "job": job,
                "status": "failed",
                "error": job.get("error_message") or "backtest failed",
            }
        if status not in ("pending", "running"):
            return {"job": job, "status": status, "error": f"unexpected status: {status}"}

        time.sleep(poll_interval_sec)

    return {
        "error": f"timeout after {timeout_sec}s",
        "code": "timeout",
        "job_id": job_id,
        "last_status": last_status,
    }
