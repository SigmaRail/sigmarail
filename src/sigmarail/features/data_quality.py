"""Read-only coverage and temporal-quality diagnostics for research datasets."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

_DATASETS = (
    "screener_price_tech_daily",
    "screener_ratings_daily",
    "screener_fundamentals_daily",
    "screener_estimates_daily",
    "screener_ownership_daily",
    "screener_factor_daily",
    "screener_forecast_models_daily",
    "screener_forward_returns_daily",
    "market_context_daily",
)


def data_quality_report(client: Any, *, start_date: str, end_date: str) -> dict[str, Any]:
    """Return a reproducible coverage ledger and ownership availability audit.

    This endpoint deliberately reports diagnostics, not certification. It does
    not infer point-in-time availability from an event date or current snapshot.
    """
    from datetime import date

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    inventory: dict[str, set[str]] = {}
    for row in client.query(
        "SELECT table, name FROM system.columns WHERE database = currentDatabase() "
        "AND table IN %(tables)s",
        parameters={"tables": list(_DATASETS)},
    ).result_rows:
        inventory.setdefault(str(row[0]), set()).add(str(row[1]))

    ledger: dict[str, Any] = {}
    for table in _DATASETS:
        cols = inventory.get(table, set())
        if not {"date", "ticker"}.issubset(cols):
            ledger[table] = {"available": False, "rows": []}
            continue
        rows = client.query(
            f"SELECT date, count() AS row_count, uniqExact(ticker) AS unique_tickers, "
            f"count() - uniqExact(tuple(ticker, date)) AS duplicate_keys "
            f"FROM {table} FINAL WHERE date BETWEEN toDate(%(start)s) AND toDate(%(end)s) "
            "GROUP BY date ORDER BY date",
            parameters={"start": start.isoformat(), "end": end.isoformat()},
        )
        ledger[table] = {
            "available": True,
            "rows": [dict(zip(rows.column_names, row)) for row in rows.result_rows],
            "sessions": len(rows.result_rows),
        }

    spine_sessions = {
        str(row["date"]) for row in ledger.get("screener_price_tech_daily", {}).get("rows", [])
    }
    label_sessions = {
        str(row["date"]) for row in ledger.get("screener_forward_returns_daily", {}).get("rows", [])
    }
    ownership: dict[str, Any] = {"available": False}
    ownership_cols = inventory.get("screener_ownership_daily", set())
    required = {"date", "inst_calendardate_complete", "inst_public_asof_date", "inst_data_lag_days"}
    if required.issubset(ownership_cols):
        audit = client.query(
            "SELECT max(date) AS audit_date, count() AS records, "
            "countIf(inst_calendardate_complete = 1) AS complete_records, "
            "countIf(inst_public_asof_date = toDate('1970-01-01') OR isNull(inst_public_asof_date)) AS unknown_public_dates, "
            "countIf(inst_public_asof_date > date) AS future_public_dates, "
            "countIf(inst_data_lag_days > 365) AS lag_over_365d "
            "FROM screener_ownership_daily FINAL "
            "WHERE date BETWEEN toDate(%(start)s) AND toDate(%(end)s)",
            parameters={"start": start.isoformat(), "end": end.isoformat()},
        )
        ownership = {
            "available": True,
            **(dict(zip(audit.column_names, audit.result_rows[0])) if audit.result_rows else {}),
        }

    observed = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at_utc": observed,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "spine_sessions": len(spine_sessions),
        "forward_label_sessions": len(label_sessions),
        "spine_sessions_without_forward_labels": sorted(spine_sessions - label_sessions),
        "ownership_availability": ownership,
        "datasets": ledger,
        "status": "diagnostic_only",
        "certification": "not_certified",
    }
    stable_payload = {key: value for key, value in payload.items() if key != "generated_at_utc"}
    stable = json.dumps(stable_payload, sort_keys=True, default=str, separators=(",", ":"))
    payload["report_fingerprint"] = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    payload["data_quality_run_id"] = payload["report_fingerprint"][:32]
    return payload


def persist_data_quality_run(client: Any, report: dict[str, Any], *, code_commit: str = "") -> str:
    """Persist a previously computed report and its per-dataset evidence.

    The caller owns authorization and connection mode. This function is meant
    for a writer-side scheduled job; the MCP report endpoint remains read-only.
    """
    run_id = str(report.get("data_quality_run_id") or "").strip()
    if not run_id:
        raise ValueError("report must include data_quality_run_id")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    checks = []
    for dataset, data in sorted((report.get("datasets") or {}).items()):
        rows = data.get("rows") or []
        duplicate_count = sum(int(r.get("duplicate_keys") or 0) for r in rows)
        checks.append({
            "check_id": f"{dataset}.natural_key_duplicates",
            "dataset": dataset,
            "status": "pass" if duplicate_count == 0 else "warn",
            "evidence": {"duplicate_keys": duplicate_count, "sessions": len(rows)},
        })
    ownership = report.get("ownership_availability") or {}
    if ownership.get("available"):
        for field, check_id in (
            ("unknown_public_dates", "ownership.unknown_public_dates"),
            ("future_public_dates", "ownership.future_public_dates"),
            ("lag_over_365d", "ownership.lag_over_365d"),
        ):
            value = int(ownership.get(field) or 0)
            checks.append({"check_id": check_id, "dataset": "screener_ownership_daily",
                           "status": "pass" if value == 0 else "warn", "evidence": {field: value}})
    client.insert(
        "data_quality_runs",
        [[run_id, now, report["start_date"], report["end_date"], code_commit,
          report["report_fingerprint"], json.dumps(report, sort_keys=True, default=str),
          json.dumps(checks, sort_keys=True, default=str), "diagnostic_only"]],
        column_names=["run_id", "run_at_utc", "start_date", "end_date", "code_commit",
                      "report_fingerprint", "report_json", "checks_json", "status"],
    )
    return run_id
