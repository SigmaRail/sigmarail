from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import clickhouse_connect

from sigmarail.features.api_types import (
    ExportFormat,
    QueryMode,
    ScreenRequest,
    ScreenResponse,
    UniverseRunRequest,
    UniverseRunResponse,
)
from sigmarail.features.ch_settings import ClickHouseSettings
from sigmarail.features.ir.universe_query_v1 import (
    UniverseQueryV1,
    compile_universe_query_v1_range_param,
    compile_universe_query_v1_single_day_param,
    universe_v1_result_column_names,
)


def _max_rows_default() -> int:
    return int(os.environ.get("SIGMARAIL_QUERY_MAX_ROWS", "5000").strip())


def _max_export_bytes() -> int:
    return int(os.environ.get("SIGMARAIL_QUERY_MAX_EXPORT_BYTES", str(2_000_000)).strip())


def _resolve_as_of_date(client: clickhouse_connect.driver.Client, as_of: str | None) -> str:
    if as_of:
        return as_of
    row = client.query("SELECT max(date) AS d FROM screener_price_tech_daily").result_rows
    if not row or row[0][0] is None:
        raise RuntimeError("screener_price_tech_daily has no rows; cannot resolve as_of date")
    d = row[0][0]
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _rows_to_dicts(result: Any) -> list[dict[str, Any]]:
    cols = result.column_names
    return [dict(zip(cols, r)) for r in result.result_rows]

def _strip_trailing_format(sql: str) -> str:
    lines = [ln.rstrip() for ln in sql.strip().splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip().upper().startswith("FORMAT "):
        lines.pop()
    return "\n".join(lines).strip()


def _screen_inner_column_aliases(spec: UniverseQueryV1 | Any) -> frozenset[str]:
    if isinstance(spec, UniverseQueryV1):
        return universe_v1_result_column_names(spec.select, spec.computed)
    from sigmarail.features.ir.query_compile import universe_spec_result_column_names

    return universe_spec_result_column_names(spec)


def _analytical_outer_select_sql(inner_aliases: frozenset[str]) -> str:
    """Outer SELECT for ``mode=analytical``: stable keys; aggregates only when the inner CTE exposes the column."""
    parts = ["  count() AS row_count"]
    if "overall_score" in inner_aliases:
        parts.append("  avg(overall_score) AS avg_overall_score")
        parts.append("  quantileExact(0.5)(overall_score) AS median_overall_score")
    else:
        parts.append("  CAST(NULL AS Nullable(Float64)) AS avg_overall_score")
        parts.append("  CAST(NULL AS Nullable(Float64)) AS median_overall_score")
    if "atr_14_pct" in inner_aliases:
        parts.append("  avg(atr_14_pct) AS avg_atr_14_pct")
        parts.append("  quantileExact(0.5)(atr_14_pct) AS median_atr_14_pct")
    else:
        parts.append("  CAST(NULL AS Nullable(Float64)) AS avg_atr_14_pct")
        parts.append("  CAST(NULL AS Nullable(Float64)) AS median_atr_14_pct")
    return ",\n".join(parts)


def _parse_json_each_row(payload: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: dict[str, Any]


class ClickHouseExecutor:
    """Execute ``universe_query_v1`` against ClickHouse L7 screener joins."""

    def __init__(self, settings: ClickHouseSettings):
        from sigmarail.features.ch_settings import connect_clickhouse

        self._settings = settings
        self._client = connect_clickhouse(settings)
        from sigmarail.features.ir.universe_v1_column_registry import try_refresh_universe_v1_columns_from_client

        try_refresh_universe_v1_columns_from_client(self._client)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def run_screen(self, req: ScreenRequest) -> ScreenResponse:
        """
        Run a single-day screen.

        detail: returns rows (list[dict])
        analytical: returns summary only (small dict), no rows
        export: returns text (csv/ndjson) or base64 is deferred to REST layer
        """
        as_of = _resolve_as_of_date(self._client, req.as_of_date)

        sql, params = compile_universe_query_v1_single_day_param(req.spec)
        params["day"] = as_of

        # Apply extra cap (defense-in-depth)
        hard_lim = min(_max_rows_default(), int(req.limit) if req.limit else _max_rows_default())

        # Ensure query has a sane LIMIT if spec omitted it (UniverseSpec enforces limit_per_day when criteria set).
        # For legacy specs, the compiled query already has LIMIT n BY date / LIMIT n.
        params["lim"] = min(int(params.get("lim") or hard_lim), hard_lim)
        sql_limited = sql  # already includes LIMIT {lim:UInt32}

        if req.mode == "analytical":
            # Compute small aggregates on the filtered set by wrapping the compiled SQL as a subquery.
            inner_aliases = _screen_inner_column_aliases(req.spec)
            outer_sel = _analytical_outer_select_sql(inner_aliases)
            q = f"""
WITH filtered AS (
  {sql_limited}
)
SELECT
{outer_sel}
FROM filtered
"""
            r = self._client.query(q, parameters=params)
            row = _rows_to_dicts(r)[0]
            return ScreenResponse(as_of_date=as_of, mode=req.mode, row_count=int(row["row_count"]), summary=row)

        if req.mode == "export" and req.export_format != "objects":
            fmt = _format_suffix(req.export_format)
            raw = self._client.raw_query(f"{sql_limited}\nFORMAT {fmt}", parameters=params)
            if not isinstance(raw, (bytes, bytearray)):
                raw = str(raw).encode("utf-8")
            truncated = False
            b = bytes(raw)
            mx = _max_export_bytes()
            if len(b) > mx:
                b = b[:mx]
                truncated = True
            return ScreenResponse(
                as_of_date=as_of,
                mode=req.mode,
                row_count=hard_lim,
                export_format=req.export_format,
                text=b.decode("utf-8", errors="replace"),
                truncated=truncated,
            )

        # Default: structured rows (execute as JSONEachRow and parse lines)
        payload = self._client.raw_query(f"{sql_limited}\nFORMAT JSONEachRow", parameters=params)
        if not isinstance(payload, (bytes, bytearray)):
            payload_b = str(payload).encode("utf-8")
        else:
            payload_b = bytes(payload)
        rows = _parse_json_each_row(payload_b)
        return ScreenResponse(as_of_date=as_of, mode=req.mode, row_count=len(rows), rows=rows)

    def run_universe_range(self, req: UniverseRunRequest) -> UniverseRunResponse:
        """
        Run a range screen: returns all rows across [start_date, end_date].

        Intended for LEAN backtests where we preload a window of daily_screener.
        """
        sql, params = compile_universe_query_v1_range_param(req.spec)
        params["start"] = req.start_date
        params["end"] = req.end_date

        # Apply caps
        hard_lim = min(_max_rows_default(), int(req.limit) if req.limit else _max_rows_default())
        params["lim"] = min(int(params.get("lim") or hard_lim), hard_lim)

        if req.mode == "export" and req.export_format != "objects":
            fmt = _format_suffix(req.export_format)
            raw = self._client.raw_query(f"{sql}\nFORMAT {fmt}", parameters=params)
            if not isinstance(raw, (bytes, bytearray)):
                raw = str(raw).encode("utf-8")
            truncated = False
            b = bytes(raw)
            mx = _max_export_bytes()
            if len(b) > mx:
                b = b[:mx]
                truncated = True
            return UniverseRunResponse(
                start_date=req.start_date,
                end_date=req.end_date,
                mode=req.mode,
                row_count=hard_lim,
                export_format=req.export_format,
                text=b.decode("utf-8", errors="replace"),
                truncated=truncated,
            )

        payload = self._client.raw_query(f"{sql}\nFORMAT JSONEachRow", parameters=params)
        if not isinstance(payload, (bytes, bytearray)):
            payload_b = str(payload).encode("utf-8")
        else:
            payload_b = bytes(payload)
        rows = _parse_json_each_row(payload_b)
        return UniverseRunResponse(
            start_date=req.start_date,
            end_date=req.end_date,
            mode=req.mode,
            row_count=len(rows),
            rows=rows,
        )


def _format_suffix(fmt: ExportFormat) -> str:
    if fmt == "json_each_row":
        return "JSONEachRow"
    if fmt == "json_compact_each_row_with_names_and_types":
        return "JSONCompactEachRowWithNamesAndTypes"
    if fmt == "csv_with_names":
        return "CSVWithNames"
    if fmt == "parquet":
        return "Parquet"
    raise ValueError(f"Unsupported export_format: {fmt!r}")
