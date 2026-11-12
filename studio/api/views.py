"""DRF views — Screening Studio Phase 1 (no auth)."""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from screens.adapter import (
    ALL_SCREEN_PRESETS,
    create_formula_preset,
    delete_formula_preset,
    get_formula_preset,
    get_market_context,
    list_formula_presets,
    list_screen_presets,
    list_trading_session_dates,
    preset_to_universe_spec,
    preview_screen,
    screen_turnover,
    update_formula_preset,
)
from screens.backtest import get_run_context, get_run_report, list_backtest_runs
from screens.backtest_jobs import get_job_status, get_spec_by_ir_id, list_specs
from screens.ch import get_ch_client
from screens.run_artifacts import (
    compare_runs,
    get_run_artifact_preview,
    get_run_asset_allocation_treemap,
    get_run_attribution,
    get_run_benchmark_comparison,
    get_run_chart_series,
    get_run_closed_trades,
    get_run_day_snapshots,
    get_run_drawdown_analytics,
    get_run_equity_curve,
    get_run_monthly_returns,
    get_run_orders,
    get_run_portfolio_exposure,
    get_run_rolling_statistics,
    get_run_trade_analytics,
    get_ticker_candles,
    list_run_artifacts,
)
from screens.ir_preview import (
    list_field_values,
    list_screen_fields,
    list_templates,
    load_template,
    preview_universe_ir,
    validate_universe_ir_spec,
    get_universe_ir_schema,
)
from screens.stock_introspection import get_stock_introspection
from screens.lineage import build_lineage_parameters, merge_lineage_into_compose
from screens.live_promotion import (
    check_promotion_gate,
    get_live_deployment_status,
    list_live_deployments,
    register_paper_deployment,
)
from screens.strategy_compose import (
    compose_vera_lab_v1,
    list_strategy_templates,
    load_framework_catalog,
    suggest_ir_id,
    validate_composed_spec,
)
from screens.optimizer import (
    create_and_launch_optimization_session,
    get_optimizer_session_heatmap,
    list_optimizer_sessions,
)
from screens.screen_store import (
    ScreenNameConflictError,
    ScreenNotFoundError,
    get_screen_repository,
)
from screens.universe_range_summary import (
    default_range_end_start,
    summarize_universe_range,
)
from screens.probe import run_probe
from screens import execution as exec_adapter
from screens import live_runtime
from screens import brokerage_catalog
from screens.credential_vault import (
    CredentialVaultError,
    credentials_configured,
    delete_credentials,
    migrate_legacy_lean_credentials,
    store_credentials,
    verify_brokerage_connection,
)
from api.models import LiveAccountProfile
from screens import spec_save


def _backtest_runner_unavailable_response() -> Response:
    return Response(
        {"detail": exec_adapter.runner_unavailable_detail()},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _resolve_universe_spec(universe: dict[str, Any]) -> dict[str, Any]:
    """Resolve universe payload to a universe_query_v1 spec dict."""
    source = str(universe.get("source") or "").strip()
    if source == "saved_screen":
        raw_id = universe.get("saved_screen_id")
        screen_id = str(raw_id or "").strip()
        if not screen_id:
            raise ValueError("saved_screen_id is required when source is saved_screen")
        try:
            screen = get_screen_repository().get(screen_id)
        except ScreenNotFoundError as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(screen.spec, dict):
            raise ValueError("saved screen spec must be an object")
        return screen.spec
    if source == "screen_preset":
        preset_id = str(universe.get("preset_id") or universe.get("preset") or "").strip()
        if not preset_id:
            raise ValueError("preset_id is required when source is screen_preset")
        return preset_to_universe_spec(preset_id)
    if source in ("inline", "inline_spec"):
        inline_spec = universe.get("inline_spec")
        if not isinstance(inline_spec, dict):
            raise ValueError("inline_spec must be an object when source is inline")
        return inline_spec
    if source == "screen_template":
        template_id = str(universe.get("screen_template_id") or "").strip()
        if not template_id:
            raise ValueError("screen_template_id is required when source is screen_template")
        tpl = load_template(template_id)
        spec = tpl.get("spec")
        if not isinstance(spec, dict):
            raise ValueError("screen template spec must be an object")
        return spec
    raise ValueError(
        "universe.source must be one of: saved_screen, screen_preset, inline, "
        "inline_spec, screen_template"
    )


class HealthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "sigmarail-studio"})


class ScreenPresetsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        return Response(list_screen_presets())


class ScreenPresetUniverseView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, preset_id: str) -> Response:
        try:
            spec = preset_to_universe_spec(preset_id)
            validate_universe_ir_spec(spec)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "preset_id": (preset_id or "").strip().lower(),
                "screen_ir": "universe_query_v1",
                "spec": spec,
            }
        )


_LINEAGE_INDEX_CACHE: dict[str, dict[str, Any]] | None = None


def _get_lineage_index() -> dict[str, dict[str, Any]]:
    global _LINEAGE_INDEX_CACHE
    if _LINEAGE_INDEX_CACHE is None:
        idx: dict[str, dict[str, Any]] = {}
        try:
            from vera_query_core.lineage.reader import _repo_root

            root = _repo_root()
            lineage_dir = root / "sql/lineage"
            if lineage_dir.is_dir():
                for p in lineage_dir.glob("*.json"):
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        target = data.get("target_table") or p.stem
                        for c_name, c_info in data.get("columns", {}).items():
                            if isinstance(c_info, dict) and (
                                c_info.get("caveats") or c_info.get("math")
                            ):
                                idx[f"{target}.{c_name}"] = {
                                    "caveats": c_info.get("caveats", []),
                                    "math": c_info.get("math"),
                                }
                                # Also index by bare column name for easy fallback
                                if c_name not in idx:
                                    idx[c_name] = idx[f"{target}.{c_name}"]
                    except Exception:
                        pass
        except Exception:
            pass
        _LINEAGE_INDEX_CACHE = idx
    return _LINEAGE_INDEX_CACHE


class ScreenFieldsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        fields = list_screen_fields()
        lineage_idx = _get_lineage_index()
        enriched_fields = []
        for f in fields:
            tbl = f.get("table") or "screener_price_tech_daily"
            col = f.get("name") or ""
            info = lineage_idx.get(f"{tbl}.{col}") or lineage_idx.get(col)
            item = dict(f)
            if info:
                if info.get("caveats"):
                    item["caveats"] = info["caveats"]
                if info.get("math"):
                    item["math"] = info["math"]
            enriched_fields.append(item)
        return Response({"fields": enriched_fields, "count": len(enriched_fields)})


class ScreenFieldLineageView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, name: str) -> Response:
        table = request.query_params.get("table")
        if not table:
            fields = list_screen_fields()
            for f in fields:
                if f.get("name") == name and f.get("table"):
                    table = f["table"]
                    break
        if not table:
            table = "screener_price_tech_daily"

        try:
            from vera_query_core.lineage.reader import explain_column_graph

            graph_data = explain_column_graph(table, name)
            return Response(
                {
                    "field": name,
                    "table": table,
                    "found": bool(graph_data.get("nodes")),
                    "caveats": graph_data.get("caveats", []),
                    "math": graph_data.get("math"),
                    "graph": graph_data,
                }
            )
        except Exception as exc:
            return Response(
                {"detail": str(exc), "field": name, "table": table},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ScreenFieldEvaluateView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, name: str) -> Response:
        ticker = (request.query_params.get("ticker") or "NVDA").strip().upper()
        as_of_date = (request.query_params.get("as_of_date") or "").strip()
        client = get_ch_client()
        try:
            clean_name = name.split(".")[-1]
            date_filter = f"AND date = '{as_of_date}'" if as_of_date else ""
            if clean_name in ("rs_rating", "momentum_rank", "composite_performance"):
                query = f"""
                    SELECT ticker, date, rs_rating, yearly_performance, performance_6m,
                           performance_3m, performance_1m, composite_performance, momentum_rank
                    FROM relative_strength
                    WHERE ticker = %(ticker)s {date_filter}
                    ORDER BY date DESC LIMIT 1
                """
                res = client.query(query, parameters={"ticker": ticker})
                if not res.result_rows:
                    return Response(
                        {"detail": f"No data found for {ticker}", "ticker": ticker},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                row = dict(zip(res.column_names, res.result_rows[0]))
                row_date = str(row["date"])
                cnt_res = client.query(
                    f"SELECT count() FROM relative_strength WHERE date = '{row_date}'"
                )
                universe_count = cnt_res.result_rows[0][0] if cnt_res.result_rows else 0

                # Cohort distribution
                dist_data = None
                cohort_pct = None
                try:
                    dist_sql = f"""
                        SELECT
                            min({clean_name}),
                            quantile(0.10)({clean_name}),
                            quantile(0.25)({clean_name}),
                            quantile(0.50)({clean_name}),
                            quantile(0.75)({clean_name}),
                            quantile(0.90)({clean_name}),
                            max({clean_name}),
                            countIf({clean_name} <= %(val)s) / count() * 100 AS pct_rank
                        FROM relative_strength
                        WHERE date = %(d)s AND isNotNull({clean_name}) AND isFinite({clean_name})
                    """
                    d_res = client.query(dist_sql, parameters={"d": row_date, "val": row.get(clean_name)})
                    if d_res.result_rows:
                        r = d_res.result_rows[0]
                        dist_data = {
                            "min": float(r[0]) if r[0] is not None else 0,
                            "p10": float(r[1]) if r[1] is not None else 0,
                            "p25": float(r[2]) if r[2] is not None else 0,
                            "median": float(r[3]) if r[3] is not None else 0,
                            "p75": float(r[4]) if r[4] is not None else 0,
                            "p90": float(r[5]) if r[5] is not None else 0,
                            "max": float(r[6]) if r[6] is not None else 0,
                        }
                        cohort_pct = float(r[7]) if r[7] is not None else None
                except Exception:
                    pass

                rank_num = row.get("momentum_rank")
                rs_num = row.get("rs_rating") or 0
                sub_latex = f"\\text{{RS}} = \\left( \\frac{{{rank_num} - 1}}{{{universe_count} - 1}} \\right) \\times 100 = {rs_num:.1f}"

                return Response(
                    {
                        "ticker": ticker,
                        "field": name,
                        "date": row_date,
                        "value": row.get(clean_name),
                        "universe_size": universe_count,
                        "rank": rank_num,
                        "distribution": dist_data,
                        "cohort_percentile": cohort_pct,
                        "substituted_latex": sub_latex,
                        "components": {
                            "perf_1y": row.get("yearly_performance"),
                            "perf_6m": row.get("performance_6m"),
                            "perf_3m": row.get("performance_3m"),
                            "perf_1m": row.get("performance_1m"),
                            "blended_score": row.get("composite_performance"),
                        },
                        "steps": [
                            f"1. Multi-horizon returns: 6m={row.get('performance_6m', 0) or 0:+.2%}, 3m={row.get('performance_3m', 0) or 0:+.2%}, 1m={row.get('performance_1m', 0) or 0:+.2%}",
                            f"2. Blended cross-sectional weighted score: {row.get('composite_performance', 0) or 0:.4f}",
                            f"3. Universe cross-sectional rank: #{rank_num} of {universe_count} active liquid equities on {row_date}",
                            f"4. Final {clean_name}: {row.get(clean_name, 0):.1f}",
                        ],
                    }
                )
            else:
                table = (request.query_params.get("table") or "").strip()
                if not table:
                    fields = list_screen_fields()
                    for f in fields:
                        if (
                            f.get("name") == name
                            or f.get("prefixed_name") == name
                            or f.get("name") == clean_name
                        ) and f.get("table"):
                            table = f["table"]
                            break
                if not table:
                    table = "screener_price_tech_daily"

                has_ticker = table != "market_context_daily"
                if has_ticker:
                    query = f"""
                        SELECT date, {clean_name}
                        FROM {table}
                        WHERE ticker = %(ticker)s {date_filter}
                        ORDER BY date DESC LIMIT 1
                    """
                    res = client.query(query, parameters={"ticker": ticker})
                else:
                    date_where = f"WHERE date = '{as_of_date}'" if as_of_date else ""
                    query = f"""
                        SELECT date, {clean_name}
                        FROM {table}
                        {date_where}
                        ORDER BY date DESC LIMIT 1
                    """
                    res = client.query(query)

                if not res.result_rows:
                    return Response(
                        {"detail": f"No data found for {ticker}", "ticker": ticker},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                row_date = str(res.result_rows[0][0])
                val = res.result_rows[0][1]

                # Enrich steps with lineage metadata if available
                lineage_idx = _get_lineage_index()
                info = lineage_idx.get(f"{table}.{clean_name}") or lineage_idx.get(clean_name)
                steps = [f"Source table: {table}"]
                sub_latex = None
                if info and info.get("math"):
                    m = info["math"]
                    if m.get("description"):
                        steps.append(f"Definition: {m['description']}")
                    elif m.get("sql_pattern"):
                        steps.append(f"Formula: {m['sql_pattern']}")
                    if m.get("latex"):
                        latex_template = m["latex"]
                        if isinstance(val, (int, float)) and not isinstance(val, bool):
                            sub_latex = f"{latex_template} = {val:.2f}"
                steps.append(f"Value for {ticker} on {row_date}: {val}")

                # Calculate Cohort Distribution if numeric and table has ticker
                dist_data = None
                cohort_pct = None
                if isinstance(val, (int, float)) and not isinstance(val, bool) and has_ticker:
                    try:
                        dist_sql = f"""
                            SELECT
                                min({clean_name}),
                                quantile(0.10)({clean_name}),
                                quantile(0.25)({clean_name}),
                                quantile(0.50)({clean_name}),
                                quantile(0.75)({clean_name}),
                                quantile(0.90)({clean_name}),
                                max({clean_name}),
                                countIf({clean_name} <= %(val)s) / count() * 100 AS pct_rank
                            FROM {table}
                            WHERE date = %(d)s AND isNotNull({clean_name}) AND isFinite({clean_name})
                        """
                        d_res = client.query(dist_sql, parameters={"d": row_date, "val": val})
                        if d_res.result_rows:
                            r = d_res.result_rows[0]
                            dist_data = {
                                "min": float(r[0]) if r[0] is not None else 0,
                                "p10": float(r[1]) if r[1] is not None else 0,
                                "p25": float(r[2]) if r[2] is not None else 0,
                                "median": float(r[3]) if r[3] is not None else 0,
                                "p75": float(r[4]) if r[4] is not None else 0,
                                "p90": float(r[5]) if r[5] is not None else 0,
                                "max": float(r[6]) if r[6] is not None else 0,
                            }
                            cohort_pct = float(r[7]) if r[7] is not None else None
                    except Exception:
                        pass

                return Response(
                    {
                        "ticker": ticker,
                        "field": name,
                        "date": row_date,
                        "value": val,
                        "distribution": dist_data,
                        "cohort_percentile": cohort_pct,
                        "substituted_latex": sub_latex,
                        "components": {},
                        "steps": steps,
                    }
                )
        except Exception as exc:
            return Response(
                {"detail": str(exc), "ticker": ticker, "field": name},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            client.close()


class ScreenFieldValuesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, name: str) -> Response:
        q = str(request.query_params.get("q") or "")
        try:
            limit = int(request.query_params.get("limit") or 40)
        except ValueError:
            limit = 40
        try:
            values = list_field_values(name, q=q, limit=limit)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"name": name, "values": values, "count": len(values)})


class ScreenFieldAlphaPerformanceView(APIView):
    """Pre-LEAN factor-performance evaluation (VeraProjects#70/#74).

    Delegates in-process to
    ``vera_query_core.alpha_evaluation.evaluate_factor_performance`` — quantile
    forward-return spread, daily Spearman IC/ICIR, regime-partitioned top-bucket
    active spread, and a pass/fail/insufficient_data verdict.
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, name: str) -> Response:
        start = (request.query_params.get("start") or "").strip()
        end = (request.query_params.get("end") or "").strip()
        horizon = (request.query_params.get("horizon") or "5d").strip()
        quantiles_raw = request.query_params.get("quantiles") or "10"
        table = (request.query_params.get("table") or "").strip()

        if not start or not end:
            return Response(
                {"detail": "start and end are required (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if horizon not in ("5d", "21d"):
            return Response(
                {"detail": f"horizon must be 5d or 21d, got {horizon!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            quantiles = int(quantiles_raw)
        except ValueError:
            return Response(
                {"detail": "quantiles must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (2 <= quantiles <= 20):
            return Response(
                {"detail": "quantiles must be in [2, 20]"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        clean_name = name.split(".")[-1]
        if not table:
            for f in list_screen_fields():
                if (
                    f.get("name") == name
                    or f.get("prefixed_name") == name
                    or f.get("name") == clean_name
                ) and f.get("table"):
                    table = f["table"]
                    break
        if not table:
            table = "screener_price_tech_daily"

        client = get_ch_client()
        try:
            from vera_query_core.alpha_evaluation import evaluate_factor_performance

            return Response(
                evaluate_factor_performance(
                    client,
                    factor_column=clean_name,
                    factor_table=table,
                    start_date=start,
                    end_date=end,
                    quantiles=quantiles,
                    horizon=horizon,
                )
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse evaluation failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            client.close()


class ScreenPreviewView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        as_of = str(body.get("as_of") or "").strip()
        if not as_of:
            return Response({"detail": "as_of is required"}, status=status.HTTP_400_BAD_REQUEST)
        preset = str(body.get("preset") or "leaders").strip().lower()
        if preset not in ALL_SCREEN_PRESETS:
            return Response(
                {"detail": f"unknown screen preset {preset!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            limit = int(body.get("limit") or 50)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        tickers = body.get("tickers")
        if tickers is not None and not isinstance(tickers, list):
            return Response({"detail": "tickers must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = preview_screen(
                client,
                as_of=as_of,
                preset=preset,
                limit=limit,
                tickers=tickers,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class ScreenLatestTradingDateView(APIView):
    """Return the most recent date with screener data in ClickHouse."""
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            client = get_ch_client()
            result = client.query(
                "SELECT max(date) as latest FROM screener_price_tech_daily WHERE date <= today()",
                settings={"allow_experimental_analyzer": 0},
            )
            rows = result.result_rows
            latest = str(rows[0][0]) if rows and rows[0][0] else None
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"latest_date": latest})


class ScreenPreviewIrView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        as_of = str(body.get("as_of") or "").strip()
        if not as_of:
            return Response({"detail": "as_of is required"}, status=status.HTTP_400_BAD_REQUEST)
        spec = body.get("spec")
        if spec is None:
            return Response({"detail": "spec is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        # Validate/compile before opening ClickHouse.
        try:
            validate_universe_ir_spec(spec)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = preview_universe_ir(client, as_of=as_of, spec_dict=spec)
            # Auto-fallback: if today returns 0 rows, retry with the most recent trading date
            if out.get("count", 0) == 0:
                fb_result = client.query(
                    "SELECT max(date) FROM screener_price_tech_daily WHERE date < {as_of:Date}",
                    parameters={"as_of": as_of},
                    settings={"allow_experimental_analyzer": 0},
                )
                fb_rows = fb_result.result_rows
                fallback_date = str(fb_rows[0][0]) if fb_rows and fb_rows[0][0] else None
                if fallback_date and fallback_date != as_of:
                    out = preview_universe_ir(client, as_of=fallback_date, spec_dict=spec)
                    out["as_of_requested"] = as_of
                    out["as_of_fallback"] = fallback_date
            if bool(body.get("include_tenure")):
                from screens.universe_range_summary import (
                    default_range_end_start,
                    membership_tenure_by_ticker,
                )

                asof_eff = str(out.get("as_of") or as_of)
                tenure_start = str(body.get("tenure_start") or body.get("start_date") or "").strip()
                if not tenure_start:
                    tenure_start, _ = default_range_end_start(end_date=asof_eff)
                rows = list(out.get("rows") or [])
                tickers = [str(r.get("ticker") or "").upper() for r in rows if r.get("ticker")]
                try:
                    tenure = membership_tenure_by_ticker(
                        client,
                        spec=spec,
                        start_date=tenure_start,
                        asof=asof_eff,
                        tickers=tickers or None,
                    )
                    for r in rows:
                        t = str(r.get("ticker") or "").upper()
                        r["days_in_universe"] = int(tenure.get(t, 0))
                    cols = list(out.get("columns") or [])
                    if "days_in_universe" not in cols:
                        cols.append("days_in_universe")
                    out["columns"] = cols
                    out["rows"] = rows
                except Exception:
                    for r in rows:
                        r.setdefault("days_in_universe", None)
                    out["rows"] = rows
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)



class ScreenCompileSqlView(APIView):
    """Compile ``universe_query_v1`` to ClickHouse SQL without executing (Studio preview)."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        spec = body.get("spec")
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _parsed, sql, params = validate_universe_ir_spec(spec)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "sql": sql.strip(),
                "params": {k: params[k] for k in sorted(params)},
            }
        )


class ScreenUniverseRangeSummaryView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        spec = body.get("spec")
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        end_date = str(body.get("end_date") or "").strip()
        start_date = str(body.get("start_date") or "").strip()
        if not end_date:
            return Response({"detail": "end_date is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not start_date:
            start_date, end_date = default_range_end_start(end_date=end_date)
        try:
            validate_universe_ir_spec(spec)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = summarize_universe_range(
                client,
                spec=spec,
                start_date=start_date,
                end_date=end_date,
                include_weekly_samples=bool(body.get("include_weekly_samples")),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class ScreenProbeView(APIView):
    """C-SCREEN-PROBE-V1: stage-prefix probe (layers / asof / range / diff)."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        view = str(body.get("view") or "layers").strip().lower()
        client = None
        try:
            if view != "layers":
                client = get_ch_client()
            out = run_probe(body, client=client)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"probe error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class ScreenAsOfRangeView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit") or 10000)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            dates = list_trading_session_dates(client, limit=limit)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"dates": dates, "count": len(dates)})


class MarketContextView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        start_date = str(request.query_params.get("start_date") or "").strip()
        end_date = str(request.query_params.get("end_date") or "").strip()
        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            limit = int(request.query_params.get("limit") or 2000)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = get_ch_client()
            out = get_market_context(client, start_date=start_date, end_date=end_date, limit=limit)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class StockIntrospectionView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        ticker = str(request.query_params.get("ticker") or "").strip().upper()
        if not ticker:
            return Response({"detail": "ticker is required"}, status=status.HTTP_400_BAD_REQUEST)
        as_of = str(request.query_params.get("as_of") or "").strip()
        if not as_of:
            return Response({"detail": "as_of is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            history_days = int(request.query_params.get("history_days") or 2500)
            forward_days = int(request.query_params.get("forward_days") or 90)
        except (TypeError, ValueError):
            return Response({"detail": "history_days and forward_days must be integers"}, status=status.HTTP_400_BAD_REQUEST)
        include_dossier_raw = request.query_params.get("include_dossier")
        include_dossier: bool | None
        if include_dossier_raw is None or str(include_dossier_raw).strip() == "":
            include_dossier = None
        else:
            include_dossier = str(include_dossier_raw).strip().lower() in ("1", "true", "yes")
        try:
            client = get_ch_client()
            out = get_stock_introspection(
                client,
                ticker=ticker,
                as_of=as_of,
                history_days=history_days,
                forward_days=forward_days,
                include_dossier=include_dossier,
            )
            return Response(out)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class ScreenTurnoverView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        as_of = str(body.get("as_of") or "").strip()
        if not as_of:
            return Response({"detail": "as_of is required"}, status=status.HTTP_400_BAD_REQUEST)
        preset = str(body.get("preset") or "leaders").strip().lower()
        if preset not in ALL_SCREEN_PRESETS:
            return Response(
                {"detail": f"unknown screen preset {preset!r}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            limit = int(body.get("limit") or 50)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = screen_turnover(client, as_of=as_of, preset=preset, limit=limit)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class CatalogTemplatesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from vera_query_core.template_catalog import list_templates, summary_row

        kind = request.query_params.get("kind") or None
        status_q = request.query_params.get("status") or None
        if kind not in (None, "screener", "strategy"):
            return Response({"detail": "kind must be screener or strategy"}, status=400)
        if status_q not in (None, "active", "deprecated", "draft"):
            return Response({"detail": "status must be active, deprecated, or draft"}, status=400)
        rows = [summary_row(r) for r in list_templates(kind=kind, status=status_q)]
        return Response({"templates": rows})


class CatalogTemplateDetailView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, template_id: str) -> Response:
        from vera_query_core.template_catalog import get_template

        try:
            return Response(get_template(template_id))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class ScreenTemplatesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        return Response({"templates": list_templates()})


class ScreenTemplateDetailView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, template_id: str) -> Response:
        try:
            data = load_template(template_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class SavedScreensView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            repo = get_screen_repository()
            rows = [s.to_dict() for s in repo.list()]
        except Exception as exc:
            return Response(
                {"detail": f"screen store error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"screens": rows, "count": len(rows)})

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        name = str(body.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        spec = body.get("spec")
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        source_template_id = str(body.get("source_template_id") or "").strip()
        try:
            screen = get_screen_repository().create(
                name=name,
                spec=spec,
                source_template_id=source_template_id,
            )
        except ScreenNameConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"screen store error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(screen.to_dict(), status=status.HTTP_201_CREATED)


class BacktestRunsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        strategy_id = request.query_params.get("strategy_id")
        if strategy_id is not None:
            strategy_id = str(strategy_id).strip() or None
        ir_id_param = request.query_params.get("ir_id")
        if ir_id_param is not None:
            ir_id_param = str(ir_id_param).strip() or None
        ir_content_hash_param = request.query_params.get("ir_content_hash")
        if ir_content_hash_param is not None:
            ir_content_hash_param = str(ir_content_hash_param).strip() or None
        status_param = request.query_params.get("status")
        run_type_param = request.query_params.get("run_type")
        search_param = request.query_params.get("search")

        def _to_float(v: Any) -> float | None:
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        min_sharpe = _to_float(request.query_params.get("min_sharpe"))
        min_return = _to_float(request.query_params.get("min_return"))
        max_dd = _to_float(request.query_params.get("max_dd"))
        include_jobs = request.query_params.get("include_jobs", "true").lower() in ("true", "1", "yes")

        try:
            client = get_ch_client()
            out = list_backtest_runs(
                client,
                strategy_id=strategy_id,
                ir_id=ir_id_param,
                ir_content_hash=ir_content_hash_param,
                limit=limit,
                status=status_param,
                run_type=run_type_param,
                min_sharpe=min_sharpe,
                min_return=min_return,
                max_dd=max_dd,
                search=search_param,
                include_jobs=include_jobs,
            )
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestFrameworkCatalogView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            catalog = load_framework_catalog()
        except (FileNotFoundError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            {
                "framework_catalog": catalog,
                "strategy_templates": list_strategy_templates(),
            }
        )


class BacktestComposeView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        framework = body.get("framework")
        full_spec = body.get("spec")
        template_id = str(body.get("template_id") or "").strip()
        if not template_id and not framework and not isinstance(full_spec, dict):
            return Response(
                {"detail": "template_id, framework, or spec is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not template_id:
            template_id = "custom_assembled"
        universe = body.get("universe")
        if not isinstance(universe, dict) and not isinstance(full_spec, dict):
            return Response({"detail": "universe must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        framework_overrides = body.get("framework_overrides")
        if framework_overrides is not None and not isinstance(framework_overrides, dict):
            return Response(
                {"detail": "framework_overrides must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        algorithm_parameters = body.get("algorithm_parameters")
        if algorithm_parameters is not None and not isinstance(algorithm_parameters, dict):
            return Response(
                {"detail": "algorithm_parameters must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        title = str(body.get("title") or template_id).strip()
        lineage = body.get("lineage")
        try:
            if isinstance(full_spec, dict):
                # Pipeline path: frontend pre-compiled a full VeraLabV1.
                # Validate and pass through unchanged; derive lineage from its universe.
                spec = full_spec
                vb = spec.get("VeraBase")
                universe_spec = vb.get("Universe") if isinstance(vb, dict) else None
                if not isinstance(universe_spec, dict):
                    universe_spec = (
                        _resolve_universe_spec(universe)
                        if isinstance(universe, dict)
                        else {}
                    )
                lineage_params = build_lineage_parameters(
                    universe_spec,
                    screen_id=lineage.get("studio_screen_id") if isinstance(lineage, dict) else None,
                    screen_name=(
                        str(lineage.get("studio_screen_name") or "") or None
                        if isinstance(lineage, dict)
                        else None
                    ),
                )
                if lineage_params:
                    algo = spec.setdefault("AlgorithmParameters", {})
                    if isinstance(algo, dict):
                        algo.update(lineage_params)
            else:
                universe_spec = _resolve_universe_spec(universe)
                lineage_params: dict[str, str] | None = None
                if isinstance(lineage, dict):
                    lineage_params = build_lineage_parameters(
                        universe_spec,
                        screen_id=lineage.get("studio_screen_id"),
                        screen_name=str(lineage.get("studio_screen_name") or "") or None,
                    )
                merged_algo = merge_lineage_into_compose(
                    algorithm_parameters if isinstance(algorithm_parameters, dict) else None,
                    lineage_params or build_lineage_parameters(universe_spec),
                )
                spec = compose_vera_lab_v1(
                    universe_spec=universe_spec,
                    template_id=template_id,
                    framework=framework if isinstance(framework, dict) else None,
                    framework_overrides=framework_overrides,
                    algorithm_parameters=merged_algo,
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        ok, err = validate_composed_spec(spec)
        validation = {"ok": ok, "error": err}
        lineage_out = (
            spec.get("AlgorithmParameters", {})
            if isinstance(spec.get("AlgorithmParameters"), dict)
            else {}
        )
        return Response(
            {
                "spec": spec,
                "ir_id_suggested": suggest_ir_id(title, universe_spec),
                "validation": validation,
                "lineage": {
                    "studio_spec_hash": lineage_out.get("studio_spec_hash"),
                    "studio_screen_id": lineage_out.get("studio_screen_id"),
                    "studio_screen_name": lineage_out.get("studio_screen_name"),
                },
            }
        )


class BacktestSpecsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit") or 50)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        search = (request.query_params.get("search") or "").strip()
        alpha_type = (request.query_params.get("alpha_type") or "").strip()
        universe_type = (request.query_params.get("universe_type") or "").strip()
        schema_status = (request.query_params.get("schema_status") or "").strip()
        is_template_raw = request.query_params.get("is_template")
        is_template = None
        if is_template_raw is not None:
            is_template = str(is_template_raw).lower() in ("true", "1", "yes")

        try:
            client = get_ch_client()
            out = list_specs(
                client,
                limit=limit,
                search=search,
                alpha_type=alpha_type,
                universe_type=universe_type,
                schema_status=schema_status,
                is_template=is_template,
            )
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)

    def post(self, request: Request) -> Response:
        if not exec_adapter.spec_save_available():
            return _backtest_runner_unavailable_response()
        body = request.data if isinstance(request.data, dict) else {}
        ir_id = str(body.get("ir_id") or "").strip()
        title = str(body.get("title") or "").strip()
        spec = body.get("spec")
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not title:
            return Response({"detail": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)

        notes = str(body.get("notes") or "")
        is_template = bool(body.get("is_template", False))
        category = str(body.get("category") or "").strip()
        tags = body.get("tags") or []
        expected_hash = str(body.get("expected_hash") or "").strip() or None
        force_new_version = bool(body.get("force_new_version", False))
        changelog_notes = str(body.get("changelog_notes") or "")
        pipeline_document = body.get("pipeline_document")
        pipeline_json = None
        if isinstance(pipeline_document, dict):
            pipeline_json = json.dumps(pipeline_document, separators=(",", ":"), sort_keys=True)
        elif isinstance(body.get("pipeline_json"), str) and body.get("pipeline_json"):
            pipeline_json = str(body.get("pipeline_json"))

        if expected_hash:
            try:
                client = get_ch_client()
                existing = get_spec_by_ir_id(client, ir_id)
            except Exception as exc:
                return Response(
                    {"detail": f"ClickHouse error: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            if existing is not None:
                current = str(existing.get("ir_content_hash") or "")
                if current and current != expected_hash:
                    return Response(
                        {
                            "detail": "expected_hash mismatch",
                            "ir_content_hash": current,
                            "code": "conflict",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

        if is_template:
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            prefix_note = f"[Template] Category: {category or 'General'}"
            if tag_str:
                prefix_note += f" | Tags: {tag_str}"
            if prefix_note not in notes:
                notes = f"{prefix_note}\n{notes}".strip()

        try:
            spec_json = json.dumps(spec, separators=(",", ":"), sort_keys=True)
            save_kwargs: dict[str, Any] = {
                "ir_id": ir_id,
                "title": title,
                "spec_json": spec_json,
                "notes": notes,
            }
            if pipeline_json is not None:
                save_kwargs["pipeline_json"] = pipeline_json
            # Guarded save: forks when the target spec already has runs, so an
            # existing run is never re-pointed at content it did not produce.
            out = spec_save.save_spec_guarded(
                force_fork=force_new_version,
                changelog_notes=changelog_notes,
                **save_kwargs,
            )
            out["is_template"] = is_template
            out["category"] = category or ("Custom Template" if is_template else "Custom Spec")
            # Prefer the stored form when save materialized risk rules into the
            # doc; fall back to the request body for legacy/no-seed saves.
            if pipeline_document is not None and "pipeline_document" not in out:
                out["pipeline_document"] = pipeline_document
        except spec_save.SpecGuardError as exc:
            return Response(
                {"detail": str(exc), "code": "spec_guard_failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"save_spec failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out, status=status.HTTP_201_CREATED)


class BacktestSpecDetailView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, ir_id: str) -> Response:
        ir_id = (ir_id or "").strip()
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_spec_by_ir_id(client, ir_id)
            if out is None:
                return Response(
                    {"detail": f"Spec with ir_id '{ir_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            try:
                from screens.pcm_rules import (
                    hydrate_pcm_rule_descriptions,
                    seed_pipeline_pcm_rules,
                )
                from screens.risk_rules import hydrate_rule_descriptions

                spec = out.get("spec") if isinstance(out.get("spec"), dict) else {}
                doc = (
                    out.get("pipeline_document")
                    if isinstance(out.get("pipeline_document"), dict)
                    else None
                )
                hydrate_rule_descriptions(spec, doc)
                if doc is not None:
                    seed_pipeline_pcm_rules(spec, doc)
                hydrate_pcm_rule_descriptions(spec, doc)
            except Exception:
                pass  # hydration is display-only; never block the read
            return Response(out)
        except Exception as exc:
            return Response(
                {"detail": f"Error retrieving spec: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class BacktestSpecHeadView(APIView):
    """Lightweight poll for compose spec-watch (ir_content_hash + updated_at)."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, ir_id: str) -> Response:
        ir_id = (ir_id or "").strip()
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_spec_by_ir_id(client, ir_id)
            if out is None:
                return Response(
                    {"detail": f"Spec with ir_id '{ir_id}' not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {
                    "ir_id": out.get("ir_id"),
                    "ir_content_hash": out.get("ir_content_hash"),
                    "updated_at": out.get("created_at"),
                    "title": out.get("title"),
                }
            )
        except Exception as exc:
            return Response(
                {"detail": f"Error retrieving spec head: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class BacktestSpecPipelineOpsView(APIView):
    """Apply structured pipeline ops; optional dry_run; MCP/SPA hub."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request, ir_id: str) -> Response:
        from screens.pipeline_ops import SpecConflictError, apply_pipeline_ops, compile_and_hash

        ir_id = (ir_id or "").strip()
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        body = request.data if isinstance(request.data, dict) else {}
        ops = body.get("ops")
        if not isinstance(ops, list) or not ops:
            return Response({"detail": "ops must be a non-empty array"}, status=status.HTTP_400_BAD_REQUEST)
        dry_run = bool(body.get("dry_run", True))
        expected_hash = str(body.get("expected_hash") or "").strip() or None
        retest = bool(body.get("retest", False))

        try:
            client = get_ch_client()
            existing = get_spec_by_ir_id(client, ir_id)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if existing is None:
            return Response(
                {"detail": f"Spec with ir_id '{ir_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        # Catalog git SSOT ids are fork-only; CH rows tagged is_template are editable.
        if str(ir_id).startswith("catalog:"):
            return Response(
                {"detail": "catalog ir_id is fork-only; refuse patch"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        current_hash = str(existing.get("ir_content_hash") or "")
        if expected_hash and current_hash and expected_hash != current_hash:
            return Response(
                {
                    "detail": "expected_hash mismatch",
                    "ir_content_hash": current_hash,
                    "code": "conflict",
                },
                status=status.HTTP_409_CONFLICT,
            )

        pipeline = existing.get("pipeline_document")
        if not isinstance(pipeline, dict):
            return Response(
                {
                    "detail": "spec has no authored pipeline_document; save from Studio first",
                    "code": "missing_pipeline",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            patched, changelog = apply_pipeline_ops(pipeline, ops)
            spec, new_hash = compile_and_hash(patched)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out: dict[str, Any] = {
            "ir_id": ir_id,
            "dry_run": dry_run,
            "pipeline_document": patched,
            "spec": spec,
            "ir_content_hash": new_hash,
            "changelog": changelog,
            "previous_hash": current_hash,
        }

        if retest:
            try:
                from screens.probe import run_probe

                through = body.get("through") if isinstance(body.get("through"), dict) else None
                probe_out = run_probe(
                    {
                        "view": "layers",
                        "pipeline": patched,
                        "through": through,
                        "probe_mode": str(body.get("probe_mode") or "measures"),
                    },
                    client=None,
                )
                out["probe"] = probe_out
            except Exception as exc:
                out["probe_error"] = str(exc)

        if dry_run:
            return Response(out)

        if not exec_adapter.spec_save_available():
            return _backtest_runner_unavailable_response()
        try:
            # Mirror the spec's risk rules into the doc being stored (no-op
            # when the exit stage already carries authored rules).
            from screens.risk_rules import seed_pipeline_risk_rules

            seed_pipeline_risk_rules(spec, patched)
            pipeline_json = json.dumps(patched, separators=(",", ":"), sort_keys=True)
            spec_json = json.dumps(spec, separators=(",", ":"), sort_keys=True)
            save_out = exec_adapter.save_spec(
                ir_id=ir_id,
                title=str(existing.get("title") or ir_id),
                spec_json=spec_json,
                notes=str(existing.get("notes") or ""),
                pipeline_json=pipeline_json,
            )
            out["saved"] = save_out
            out["ir_content_hash"] = save_out.get("ir_content_hash") or new_hash
        except Exception as exc:
            return Response(
                {"detail": f"save_spec failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class ExecutionHealthView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            out = exec_adapter.execution_health()
        except Exception as exc:
            return Response(
                {"detail": f"execution health check failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class ExecutionProjectsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        return Response(exec_adapter.list_lean_projects())


class BacktestJobsListView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit") or 20)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        status_filter = request.query_params.get("status")
        if status_filter is not None:
            status_filter = str(status_filter).strip() or None
        try:
            out = exec_adapter.list_recent_jobs(limit=limit, status=status_filter)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)

    def post(self, request: Request) -> Response:
        if not exec_adapter.runner_available():
            return _backtest_runner_unavailable_response()
        body = request.data if isinstance(request.data, dict) else {}
        ir_id = str(body.get("ir_id") or "").strip()
        start_date = str(body.get("start_date") or "").strip()
        end_date = str(body.get("end_date") or "").strip()
        lean_project = str(body.get("lean_project") or "VeraTradingLab").strip()
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not start_date:
            return Response({"detail": "start_date is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not end_date:
            return Response({"detail": "end_date is required"}, status=status.HTTP_400_BAD_REQUEST)
        immediate = bool(body.get("immediate", False))
        extra_env = body.get("extra_env")
        if extra_env is not None and not isinstance(extra_env, dict):
            return Response({"detail": "extra_env must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = exec_adapter.submit_backtest_job(
                ir_id=ir_id,
                start_date=start_date,
                end_date=end_date,
                lean_project=lean_project,
                immediate=immediate,
                extra_env=extra_env,
            )
        except Exception as exc:
            return Response(
                {"detail": f"backtest submit failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result, status=status.HTTP_202_ACCEPTED)


class BacktestJobLogView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, job_id: str) -> Response:
        job_id = (job_id or "").strip()
        if not job_id:
            return Response({"detail": "job_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            tail = int(request.query_params.get("tail") or 200)
        except (TypeError, ValueError):
            return Response({"detail": "tail must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = exec_adapter.get_job_log_tail(job_id, tail=tail)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"log read failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if out.get("error") == "log file not found":
            return Response({"detail": "log not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(out)


class BacktestJobStatusView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, job_id: str) -> Response:
        job_id = (job_id or "").strip()
        if not job_id:
            return Response({"detail": "job_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            row = get_job_status(client, job_id)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if row is None:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(row)


class BacktestJobCancelView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request, job_id: str) -> Response:
        job_id = (job_id or "").strip()
        if not job_id:
            return Response({"detail": "job_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            out = exec_adapter.cancel_backtest_job(job_id)
        except Exception as exc:
            return Response(
                {"detail": f"cancel failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out, status=status.HTTP_200_OK)


class BacktestRunReportView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_report(client, run_id)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if isinstance(out, dict) and out.get("code") == "not_found":
            return Response({"detail": out.get("error", "not found")}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(out, dict) and out.get("code") == "invalid_argument":
            return Response({"detail": out.get("error", "invalid argument")}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class BacktestRunContextView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            trades_limit = int(request.query_params.get("trades_limit") or 50)
        except (TypeError, ValueError):
            return Response({"detail": "trades_limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_context(client, run_id, trades_limit=trades_limit)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if isinstance(out, dict) and out.get("code") == "not_found":
            return Response({"detail": out.get("error", "not found")}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(out, dict) and out.get("code") == "invalid_argument":
            return Response({"detail": out.get("error", "invalid argument")}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class BacktestRunArtifactsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = list_run_artifacts(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunArtifactPreviewView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str, artifact_type: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_artifact_preview(client, run_id, artifact_type)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunEquityView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_equity_curve(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunOrdersView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.query_params.get("limit") or 200)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        symbol = (request.query_params.get("symbol") or request.query_params.get("campaign") or "").strip() or None
        order_id = (request.query_params.get("order_id") or request.query_params.get("id") or "").strip() or None
        try:
            client = get_ch_client()
            out = get_run_orders(client, run_id, limit=limit, symbol=symbol, order_id=order_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunClosedTradesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.query_params.get("limit") or 500)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        symbol = (request.query_params.get("symbol") or request.query_params.get("campaign") or "").strip() or None
        trade_id = (request.query_params.get("trade_id") or request.query_params.get("id") or "").strip() or None
        try:
            client = get_ch_client()
            out = get_run_closed_trades(client, run_id, limit=limit, symbol=symbol, trade_id=trade_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunChartSeriesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        chart = (request.query_params.get("chart") or "").strip()
        series = (request.query_params.get("series") or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not chart or not series:
            return Response(
                {"detail": "chart and series query params are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            client = get_ch_client()
            out = get_run_chart_series(client, run_id, chart=chart, series=series)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunDaySnapshotsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_day_snapshots(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunMonthlyReturnsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_monthly_returns(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunTradeAnalyticsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_trade_analytics(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunAttributionView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_attribution(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunDrawdownsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_drawdown_analytics(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunBenchmarkComparisonView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        benchmark = (request.query_params.get("benchmark") or "SPY").strip().upper()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_benchmark_comparison(client, run_id, benchmark=benchmark)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunAssetAllocationView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_asset_allocation_treemap(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunPortfolioExposureView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_portfolio_exposure(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestRunRollingStatsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, run_id: str) -> Response:
        run_id = (run_id or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_run_rolling_statistics(client, run_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestCandlesView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        ticker = (request.query_params.get("ticker") or "").strip().upper()
        start_date = (request.query_params.get("start_date") or "").strip()
        end_date = (request.query_params.get("end_date") or "").strip()
        if not ticker:
            return Response({"detail": "ticker query param is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not start_date or not end_date:
            return Response({"detail": "start_date and end_date query params are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_ticker_candles(client, ticker, start_date, end_date)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class BacktestCompareRunsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        raw_ids = request.query_params.get("run_ids") or ""
        run_ids = [r.strip() for r in raw_ids.split(",") if r.strip()]
        if not run_ids:
            return Response(
                {"detail": "run_ids query param is required (comma-separated)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            client = get_ch_client()
            out = compare_runs(client, run_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)


class LiveDeploymentsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit") or 20)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = list_live_deployments(client, limit=limit)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out)

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        ir_id = str(body.get("ir_id") or "").strip()
        approval_backtest_run_id = str(body.get("approval_backtest_run_id") or "").strip()
        deployment_id = str(body.get("deployment_id") or "").strip() or str(uuid.uuid4())
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not approval_backtest_run_id:
            return Response(
                {"detail": "approval_backtest_run_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            client = get_ch_client()
            out = register_paper_deployment(
                client,
                deployment_id=deployment_id,
                ir_id=ir_id,
                approval_backtest_run_id=approval_backtest_run_id,
            )
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("not_found:"):
                return Response({"detail": msg}, status=status.HTTP_404_NOT_FOUND)
            if msg.startswith("job_not_done:") or msg.startswith("ir_mismatch:"):
                return Response({"detail": msg}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(out, status=status.HTTP_201_CREATED)


class LiveDeploymentStatusView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, deployment_id: str) -> Response:
        deployment_id = (deployment_id or "").strip()
        if not deployment_id:
            return Response({"detail": "deployment_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_live_deployment_status(client, deployment_id)
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if isinstance(out, dict) and out.get("code") == "not_found":
            return Response({"detail": out.get("error", "not found")}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(out, dict) and out.get("code") == "invalid_argument":
            return Response({"detail": out.get("error", "invalid argument")}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class LivePromotionGateView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        ir_id = str(request.query_params.get("ir_id") or "").strip()
        run_id = str(request.query_params.get("approval_backtest_run_id") or "").strip()
        if not ir_id:
            return Response({"detail": "ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not run_id:
            return Response(
                {"detail": "approval_backtest_run_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            client = get_ch_client()
            out = check_promotion_gate(
                client,
                approval_backtest_run_id=run_id,
                ir_id=ir_id,
            )
        except Exception as exc:
            return Response(
                {"detail": f"ClickHouse error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if not out.get("ok"):
            code = out.get("code", "promotion_denied")
            if code == "not_found":
                return Response(out, status=status.HTTP_404_NOT_FOUND)
            if code in ("job_not_done", "ir_mismatch"):
                return Response(out, status=status.HTTP_409_CONFLICT)
            return Response(out, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class LocalLiveRuntimeView(APIView):
    """Narrow, opt-in local controller for the Alpaca paper LEAN container."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        if not live_runtime.request_is_loopback(request.META.get("REMOTE_ADDR")):
            return Response({"detail": "Local LEAN status is available only from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(live_runtime.runtime_status())
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        try:
            action = str(body.get("action") or "").strip()
            if action in {"start-paper", "start-live"}:
                result = live_runtime.start_deployment(
                    remote_addr=request.META.get("REMOTE_ADDR"),
                    origin=request.headers.get("Origin"),
                    host=request.get_host(),
                    ir_id=str(body.get("ir_id") or ""),
                    approval_backtest_run_id=str(body.get("approval_backtest_run_id") or ""),
                    profile_id=str(body.get("account_profile_id") or "") or None,
                    expected_environment="paper" if action == "start-paper" else "live",
                    live_confirmation=str(body.get("live_confirmation") or "") or None,
                )
            elif action in {"stop", "liquidate"}:
                result = live_runtime.control_paper_deployment(
                    remote_addr=request.META.get("REMOTE_ADDR"),
                    origin=request.headers.get("Origin"),
                    host=request.get_host(),
                    action=action,
                    deployment_id=str(body.get("deployment_id") or "") or None,
                    confirmation=str(body.get("confirmation") or "") or None,
                )
            else:
                return Response({"detail": "Unsupported local deployment action"}, status=status.HTTP_400_BAD_REQUEST)
        except live_runtime.RuntimeErrorDetail as exc:
            message = str(exc)
            code = status.HTTP_403_FORBIDDEN if "disabled" in message or "local machine" in message else status.HTTP_409_CONFLICT
            return Response({"detail": message}, status=code)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"detail": "Local LEAN control failed; inspect the Studio server log and LEAN output."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result, status=status.HTTP_200_OK)


class LiveAccountProfilesView(APIView):
    """Account connection metadata in SQLite; broker secrets remain in OS keyring."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    @staticmethod
    def _serialize(profile: LiveAccountProfile) -> dict[str, Any]:
        return {
            "id": str(profile.pk),
            "provider": profile.provider,
            "data_provider": profile.data_provider,
            "environment": profile.environment,
            "display_name": profile.display_name,
            "account_identifier": profile.account_identifier,
            "active": profile.active,
            "credentials_configured": credentials_configured(profile),
            "connection_verification_available": profile.provider == "alpaca",
            "updated_at": profile.updated_at.isoformat(),
        }

    def get(self, request: Request) -> Response:
        if not live_runtime.request_is_loopback(request.META.get("REMOTE_ADDR")):
            return Response({"detail": "Account profiles are available only from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        profiles = LiveAccountProfile.objects.order_by("-updated_at")
        try:
            return Response({"profiles": [self._serialize(item) for item in profiles]})
        except CredentialVaultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request: Request) -> Response:
        if not live_runtime.request_is_local_control(
            request.META.get("REMOTE_ADDR"), request.headers.get("Origin"), request.get_host()
        ):
            return Response({"detail": "Account setup requires a same-origin request from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        body = request.data if isinstance(request.data, dict) else {}
        provider = str(body.get("provider") or "alpaca").strip().lower()
        environment = str(body.get("environment") or "paper").strip().lower()
        try:
            descriptor = brokerage_catalog.get_brokerage(provider)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if environment not in descriptor["environments"]:
            return Response({"detail": "The selected environment is not supported by this LEAN brokerage"}, status=status.HTTP_400_BAD_REQUEST)
        data_provider = str(body.get("data_provider") or descriptor["default_data_provider"]).strip().lower()
        try:
            brokerage_catalog.get_data_provider(data_provider)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        display_name = str(body.get("display_name") or f"{descriptor['label']} {environment}").strip()[:80]
        account_identifier = str(body.get("account_identifier") or "").strip()[:128]
        credentials = body.get("credentials") if isinstance(body.get("credentials"), dict) else {}
        # Existing first-run Alpaca UI sent generic field names. Continue accepting
        # those while all new profiles use LEAN's canonical config keys.
        if provider == "alpaca" and set(credentials).issubset({"api_key", "api_secret"}):
            credentials = {
                **({"alpaca-api-key": credentials["api_key"]} if credentials.get("api_key") else {}),
                **({"alpaca-api-secret": credentials["api_secret"]} if credentials.get("api_secret") else {}),
            }
        try:
            cleaned_credentials = brokerage_catalog.validate_credentials(provider, credentials, data_provider) if credentials else {}
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        profile_id = str(body.get("id") or "").strip()
        if profile_id:
            try:
                profile = LiveAccountProfile.objects.get(pk=profile_id)
            except (LiveAccountProfile.DoesNotExist, ValueError):
                return Response({"detail": "Account profile not found"}, status=status.HTTP_404_NOT_FOUND)
            if profile.provider != provider or profile.environment != environment or profile.data_provider != data_provider:
                return Response({"detail": "Create a new profile to change brokerage, data provider, or environment"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            import uuid
            profile_id = uuid.uuid4()
            profile = LiveAccountProfile(
                id=profile_id,
                provider=provider,
                data_provider=data_provider,
                environment=environment,
                keyring_service=f"sigmarail-studio/broker/{profile_id}",
            )
            profile.active = True
        profile.display_name = display_name
        profile.account_identifier = account_identifier
        try:
            with live_runtime.profile_management_lock():
                profile.save()
                if cleaned_credentials:
                    store_credentials(profile, cleaned_credentials)
                    # Only the original Alpaca paper profile is eligible for the legacy
                    # lean.json migration/scrub path.
                    if provider == "alpaca" and environment == "paper":
                        migrate_legacy_lean_credentials(profile)
                elif provider == "alpaca" and environment == "paper":
                    migrate_legacy_lean_credentials(profile)
        except CredentialVaultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except live_runtime.RuntimeErrorDetail as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self._serialize(profile), status=status.HTTP_200_OK)


class LiveBrokerageCatalogView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        if not live_runtime.request_is_loopback(request.META.get("REMOTE_ADDR")):
            return Response({"detail": "Brokerage options are available only from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            "brokerages": brokerage_catalog.public_catalog(),
            "data_providers": brokerage_catalog.public_data_provider_catalog(),
        })


class LiveAccountProfileView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def patch(self, request: Request, profile_id: str) -> Response:
        if not live_runtime.request_is_local_control(
            request.META.get("REMOTE_ADDR"), request.headers.get("Origin"), request.get_host()
        ):
            return Response({"detail": "Account setup requires a same-origin request from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        active = request.data.get("active") if isinstance(request.data, dict) else None
        if not isinstance(active, bool):
            return Response({"detail": "active must be a boolean"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = LiveAccountProfile.objects.get(pk=profile_id)
        except (LiveAccountProfile.DoesNotExist, ValueError):
            return Response({"detail": "Account profile not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            with live_runtime.profile_management_lock():
                profile.active = active
                profile.save(update_fields=["active", "updated_at"])
        except live_runtime.RuntimeErrorDetail as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(LiveAccountProfilesView._serialize(profile))

    def post(self, request: Request, profile_id: str) -> Response:
        if not live_runtime.request_is_local_control(
            request.META.get("REMOTE_ADDR"), request.headers.get("Origin"), request.get_host()
        ):
            return Response({"detail": "Account setup requires a same-origin request from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        try:
            profile = LiveAccountProfile.objects.get(pk=profile_id)
        except (LiveAccountProfile.DoesNotExist, ValueError):
            return Response({"detail": "Account profile not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Response(verify_brokerage_connection(profile))
        except CredentialVaultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def delete(self, request: Request, profile_id: str) -> Response:
        if not live_runtime.request_is_local_control(
            request.META.get("REMOTE_ADDR"), request.headers.get("Origin"), request.get_host()
        ):
            return Response({"detail": "Account setup requires a same-origin request from the local machine"}, status=status.HTTP_403_FORBIDDEN)
        try:
            profile = LiveAccountProfile.objects.get(pk=profile_id)
        except (LiveAccountProfile.DoesNotExist, ValueError):
            return Response({"detail": "Account profile not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            with live_runtime.profile_management_lock():
                if live_runtime.account_profile_is_in_use(str(profile.pk)):
                    return Response(
                        {"detail": "This account is used by an active or starting LEAN deployment; disable it after stopping the deployment, then delete it."},
                        status=status.HTTP_409_CONFLICT,
                    )
                delete_credentials(profile)
                profile.delete()
        except CredentialVaultError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except live_runtime.RuntimeErrorDetail as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedScreenDetailView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, screen_id: str) -> Response:
        try:
            screen = get_screen_repository().get(str(screen_id))
        except ScreenNotFoundError:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response(
                {"detail": f"screen store error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(screen.to_dict())

    def put(self, request: Request, screen_id: str) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        name = None
        spec = None
        source_template_id = None
        if "name" in body:
            name = str(body.get("name") or "").strip()
            if not name:
                return Response(
                    {"detail": "name must be non-empty"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "spec" in body:
            spec = body.get("spec")
            if not isinstance(spec, dict):
                return Response(
                    {"detail": "spec must be an object"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "source_template_id" in body:
            source_template_id = str(body.get("source_template_id") or "").strip()
        try:
            screen = get_screen_repository().update(
                str(screen_id),
                name=name,
                spec=spec,
                source_template_id=source_template_id,
            )
        except ScreenNotFoundError:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        except ScreenNameConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"screen store error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(screen.to_dict())

    def delete(self, request: Request, screen_id: str) -> Response:
        try:
            get_screen_repository().delete(str(screen_id))
        except ScreenNotFoundError:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response(
                {"detail": f"screen store error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class OptimizerLaunchView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        base_ir_id = str(body.get("base_ir_id") or "").strip()
        if not base_ir_id:
            return Response({"detail": "base_ir_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        start_date = str(body.get("start_date") or "").strip()
        end_date = str(body.get("end_date") or "").strip()
        if not start_date or not end_date:
            return Response({"detail": "start_date and end_date are required"}, status=status.HTTP_400_BAD_REQUEST)

        param_x_name = str(body.get("param_x_name") or "").strip()
        param_x_values = body.get("param_x_values")
        if not param_x_name or not isinstance(param_x_values, list) or not param_x_values:
            return Response({"detail": "param_x_name and non-empty param_x_values list are required"}, status=status.HTTP_400_BAD_REQUEST)

        param_y_name = str(body.get("param_y_name") or "").strip() or None
        param_y_values = body.get("param_y_values") if isinstance(body.get("param_y_values"), list) else None

        title = str(body.get("title") or "").strip()
        objective = str(body.get("objective") or "sharpe_ratio").strip()
        strategy_type = str(body.get("strategy_type") or "euler").strip()
        oos_days = int(body.get("oos_days") or 0)
        constraints = body.get("constraints") if isinstance(body.get("constraints"), list) else []
        max_concurrent = int(body.get("max_concurrent") or 4)
        lean_project = str(body.get("lean_project") or "VeraTradingLab").strip()

        try:
            client = get_ch_client()
            out = create_and_launch_optimization_session(
                base_ir_id=base_ir_id,
                start_date=start_date,
                end_date=end_date,
                param_x_name=param_x_name,
                param_x_values=[float(v) for v in param_x_values],
                param_y_name=param_y_name,
                param_y_values=[float(v) for v in param_y_values] if param_y_values else None,
                title=title,
                objective=objective,
                strategy_type=strategy_type,
                oos_days=oos_days,
                constraints=constraints,
                max_concurrent=max_concurrent,
                lean_project=lean_project,
                client=client,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"Optimization launch failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(out, status=status.HTTP_201_CREATED)


class OptimizerSessionsListView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit") or 20)
        try:
            client = get_ch_client()
            sessions = list_optimizer_sessions(client=client, limit=limit)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"sessions": sessions, "count": len(sessions)})


class OptimizerSessionHeatmapView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, session_id: str) -> Response:
        session_id = (session_id or "").strip()
        if not session_id:
            return Response({"detail": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            client = get_ch_client()
            out = get_optimizer_session_heatmap(session_id, client=client)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        if isinstance(out, dict) and "error" in out:
            return Response({"detail": out["error"]}, status=status.HTTP_404_NOT_FOUND)
        return Response(out)


def _system_framework_templates() -> list[dict[str, Any]]:
    from screens.strategy_compose import list_strategy_templates, _load_template_json
    out: list[dict[str, Any]] = []
    for item in list_strategy_templates():
        tid = item["id"]
        try:
            raw = _load_template_json(tid)
            fw = raw.get("Framework") or raw.get("framework") or {}
            out.append({
                "id": tid,
                "name": item["label"],
                "label": item["label"],
                "description": item["description"],
                "category": "QuantConnect Framework",
                "is_system": True,
                "framework": fw,
                "algorithm_parameters": raw.get("AlgorithmParameters") or raw.get("algorithm_parameters") or {},
            })
        except Exception:
            pass
    return out


class StrategyFrameworkTemplatesView(APIView):
    """List built-in + saved ensemble strategy framework templates, or save a new template."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from api.models import SavedStrategyTemplate

        sys_templates = _system_framework_templates()
        custom_templates = [t.to_dict() for t in SavedStrategyTemplate.objects.all()]
        all_templates = sys_templates + custom_templates
        return Response({"templates": all_templates, "count": len(all_templates)})

    def post(self, request: Request) -> Response:
        from api.models import SavedStrategyTemplate

        body = request.data if isinstance(request.data, dict) else {}
        name = str(body.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        description = str(body.get("description") or "").strip()
        category = str(body.get("category") or "Custom").strip() or "Custom"
        framework = body.get("framework")
        if not isinstance(framework, dict):
            return Response({"detail": "framework must be a valid dictionary"}, status=status.HTTP_400_BAD_REQUEST)

        sys_templates = _system_framework_templates()
        # Check conflict with system or existing template
        if any(t["name"].lower() == name.lower() or t["id"] == name for t in sys_templates):
            return Response({"detail": f"Template name '{name}' conflicts with a system blueprint"}, status=status.HTTP_409_CONFLICT)

        if SavedStrategyTemplate.objects.filter(name__iexact=name).exists():
            return Response({"detail": f"Template with name '{name}' already exists"}, status=status.HTTP_409_CONFLICT)

        template = SavedStrategyTemplate.objects.create(
            name=name,
            description=description,
            category=category,
            framework=framework,
        )
        return Response(template.to_dict(), status=status.HTTP_201_CREATED)


class StrategyFrameworkTemplateDetailView(APIView):
    """Retrieve, update, or delete a saved ensemble strategy framework template."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, template_id: str) -> Response:
        from api.models import SavedStrategyTemplate

        sys_templates = _system_framework_templates()
        # Check system templates first
        for sys_t in sys_templates:
            if sys_t["id"] == template_id or str(sys_t.get("name")) == template_id:
                return Response(sys_t)

        try:
            template = SavedStrategyTemplate.objects.get(pk=template_id)
        except (SavedStrategyTemplate.DoesNotExist, ValueError):
            try:
                template = SavedStrategyTemplate.objects.get(name=template_id)
            except SavedStrategyTemplate.DoesNotExist:
                return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(template.to_dict())

    def put(self, request: Request, template_id: str) -> Response:
        from api.models import SavedStrategyTemplate

        sys_templates = _system_framework_templates()
        if any(sys_t["id"] == template_id for sys_t in sys_templates):
            return Response({"detail": "System blueprints cannot be modified"}, status=status.HTTP_403_FORBIDDEN)

        try:
            template = SavedStrategyTemplate.objects.get(pk=template_id)
        except (SavedStrategyTemplate.DoesNotExist, ValueError):
            return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)

        body = request.data if isinstance(request.data, dict) else {}
        if "name" in body:
            name = str(body["name"] or "").strip()
            if not name:
                return Response({"detail": "name cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
            if SavedStrategyTemplate.objects.filter(name__iexact=name).exclude(pk=template.pk).exists():
                return Response({"detail": f"Template with name '{name}' already exists"}, status=status.HTTP_409_CONFLICT)
            template.name = name
        if "description" in body:
            template.description = str(body["description"] or "").strip()
        if "category" in body:
            template.category = str(body["category"] or "").strip() or "Custom"
        if "framework" in body:
            if not isinstance(body["framework"], dict):
                return Response({"detail": "framework must be a dictionary"}, status=status.HTTP_400_BAD_REQUEST)
            template.framework = body["framework"]

        template.save()
        return Response(template.to_dict())

    def delete(self, request: Request, template_id: str) -> Response:
        from api.models import SavedStrategyTemplate

        sys_templates = _system_framework_templates()
        if any(sys_t["id"] == template_id for sys_t in sys_templates):
            return Response({"detail": "System blueprints cannot be deleted"}, status=status.HTTP_403_FORBIDDEN)

        try:
            template = SavedStrategyTemplate.objects.get(pk=template_id)
        except (SavedStrategyTemplate.DoesNotExist, ValueError):
            return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)

        template.delete()
        return Response({"deleted": True, "id": template_id})

# --- Strategy pipeline endpoints -------------------------------------------
# These delegate to vera_query_core.strategy (pure data transforms, no DB).


class StrategyCompileView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from vera_query_core.strategy import PipelineDocument, compile_pipeline

        body = request.data if isinstance(request.data, dict) else {}
        try:
            doc = PipelineDocument.model_validate(body)
            spec = compile_pipeline(doc)
            # Spec-truth materialization: show the generated SwingProgressive
            # ladder in the previewed spec — the same rules save will persist
            # and the run will execute.
            from screens.risk_rules import materialize_swing_risk_rules

            materialize_swing_risk_rules(spec)
            return Response(spec)
        except Exception as exc:  # pydantic ValidationError / ValueError
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyDecompileView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from vera_query_core.strategy import decompile_pipeline

        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(decompile_pipeline(body).model_dump())
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyCompilePortfolioView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from vera_query_core.strategy import PortfolioDocument, compile_portfolio

        body = request.data if isinstance(request.data, dict) else {}
        try:
            doc = PortfolioDocument.model_validate(body)
            return Response(compile_portfolio(doc))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyDecompilePortfolioView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from vera_query_core.strategy import decompile_portfolio

        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(decompile_portfolio(body).model_dump())
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyValidateView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        from vera_query_core.strategy import PipelineDocument, compile_pipeline

        body = request.data if isinstance(request.data, dict) else {}
        try:
            doc = PipelineDocument.model_validate(body)
            compile_pipeline(doc)
            return Response({"valid": True})
        except Exception as exc:
            return Response({"valid": False, "error": str(exc)})


class StrategyFactorsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from vera_query_core.strategy import list_factors

        return Response({"factors": list_factors()})


class StrategyPositionFieldsView(APIView):
    """Runtime position bindings — the `pos` operand's vocabulary.

    Served from ``vera_lab.ir.position_bindings`` (the registry lives beside the
    runtime that supplies the context — single source, no frontend copy).
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from screens.risk_rules import _ensure_veralab_path

        _ensure_veralab_path()
        try:
            from vera_lab.ir.position_bindings import POSITION_BINDINGS
        except Exception:
            return Response({"fields": [], "count": 0})
        return Response(
            {"fields": [dict(b) for b in POSITION_BINDINGS],
             "count": len(POSITION_BINDINGS)}
        )


class StrategyPcmBindingsView(APIView):
    """PCM runtime bindings — the ``ref`` operand's namespaces (cand/hold/acct/pyr/regime).

    Served from ``vera_lab.ir.pcm_bindings`` (the registry lives beside the
    runtime that supplies the context — single source, no frontend copy).
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from screens.pcm_rules import pcm_bindings_catalog

        namespaces = pcm_bindings_catalog()
        if namespaces is None:
            return Response({"namespaces": {}, "count": 0})
        return Response(
            {
                "namespaces": namespaces,
                "count": sum(len(v) for v in namespaces.values()),
            }
        )


class StrategyEvalRulesView(APIView):
    """POST ``/api/strategy/eval-rules`` — preview-evaluate a slot rule table.

    "What would these rules decide for <ticker> on <date>?" Runs the spec's
    own universe query for the day, takes that ticker's row (the real T-1
    ``col`` row), and evaluates every rule's ``when`` with the same evaluator
    + terminality contract as the LEAN runtime.

    Body::

        {
          "ir_id": "strat-...",        // OR pass "universe" + "rules" directly
          "slot": "pcm" | "risk",      // which table (default pcm)
          "ticker": "NVDA",
          "as_of_date": "2026-10-08",  // optional; default = latest data day
          "contexts": {                // unit shape the runtime would build
            "cand": {"is_new": 1, "has_insight": 1},
            "acct": {"slots_remaining": 2}, ...
          },
          "rules": [...],              // optional override (draft table)
          "row_overrides": {...}       // optional what-if tweaks to the row
        }
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    _SLOT_PATH = {
        "pcm": ("Framework", "PortfolioConstruction"),
        "risk": ("Framework", "RiskManagement"),
    }

    def post(self, request: Request) -> Response:
        from screens.rule_eval import evaluate_rule_table, fetch_universe_row

        body = request.data if isinstance(request.data, dict) else {}
        ticker = str(body.get("ticker") or "").strip().upper()
        if not ticker:
            return Response({"detail": "ticker is required"}, status=400)
        slot = str(body.get("slot") or "pcm").strip().lower()
        fw_key, slot_key = self._SLOT_PATH.get(slot, self._SLOT_PATH["pcm"])

        spec = body.get("spec") if isinstance(body.get("spec"), dict) else None
        client = get_ch_client()
        if spec is None:
            ir_id = str(body.get("ir_id") or "").strip()
            if not ir_id:
                return Response(
                    {"detail": "ir_id or spec is required"}, status=400
                )
            rec = get_spec_by_ir_id(client, ir_id)
            if not rec:
                return Response({"detail": f"spec {ir_id} not found"}, status=404)
            spec = rec.get("spec") or {}

        rules = body.get("rules")
        if rules is None:
            slot_obj = ((spec.get(fw_key) or {}).get(slot_key) or {})
            rules = (slot_obj.get("Parameters") or {}).get("rules") or []

        universe = body.get("universe")
        if isinstance(universe, dict):
            try:
                universe_spec = _resolve_universe_spec(universe)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
        else:
            universe_spec = ((spec.get("VeraBase") or {}).get("Universe") or {})
        if not isinstance(universe_spec, dict) or not universe_spec:
            return Response(
                {"detail": "no universe_query_v1 found to fetch the ticker row"},
                status=400,
            )

        try:
            day, row = fetch_universe_row(
                client,
                universe_spec=universe_spec,
                ticker=ticker,
                as_of=str(body.get("as_of_date") or "").strip() or None,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        if row is None:
            return Response(
                {
                    "ticker": ticker,
                    "date": day,
                    "in_universe": False,
                    "row": None,
                    "per_rule": [],
                    "decision": {"rule": None, "actions": []},
                    "detail": f"{ticker} is not in this universe on {day}",
                }
            )

        overrides = body.get("row_overrides")
        if isinstance(overrides, dict):
            row = {**row, **overrides}

        out = evaluate_rule_table(
            row, rules if isinstance(rules, list) else [], body.get("contexts")
        )
        return Response(
            {
                "ticker": ticker,
                "date": day,
                "in_universe": True,
                "row": row,
                "slot": slot,
                **out,
            }
        )


class StrategyPresetsView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        from vera_query_core.strategy.presets import list_presets

        return Response({"presets": list_presets()})


class StrategyPresetDetailView(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, preset_id: str) -> Response:
        from vera_query_core.strategy.presets import get_preset

        try:
            return Response(get_preset(preset_id).model_dump())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class FormulaPresetsListView(APIView):
    """List (GET) or create (POST) formula presets.

    Combined with the detail view below, this removes the duplicate URL
    patterns that previously caused Django to route POST/PATCH/DELETE to the
    GET-only views (405 Method Not Allowed).
    """
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        active_only = request.query_params.get("active_only", "true").lower() in ("true", "1", "yes")
        try:
            client = get_ch_client()
            presets = list_formula_presets(client, active_only=active_only)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"presets": presets, "count": len(presets)})

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        label = str(body.get("label") or "").strip()
        expr = str(body.get("expr") or "").strip()
        description = str(body.get("description") or "").strip()
        category = str(body.get("category") or "Custom").strip()

        if not label:
            return Response({"detail": "label is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not expr:
            return Response({"detail": "expr is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = get_ch_client()
            preset = create_formula_preset(
                client,
                label=label,
                expr=expr,
                description=description,
                category=category,
                created_by="user",
            )
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(preset, status=status.HTTP_201_CREATED)


class FormulaPresetDetailView(APIView):
    """Get (GET), update (PATCH), or delete (DELETE) a single formula preset."""
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, preset_id: str) -> Response:
        try:
            client = get_ch_client()
            preset = get_formula_preset(client, preset_id)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        if preset is None:
            return Response({"detail": "Formula preset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(preset)

    def patch(self, request: Request, preset_id: str) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        try:
            client = get_ch_client()
            preset = update_formula_preset(
                client,
                preset_id,
                label=body.get("label"),
                expr=body.get("expr"),
                description=body.get("description"),
                category=body.get("category"),
                is_active=body.get("is_active"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        if preset is None:
            return Response({"detail": "Formula preset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(preset)

    def delete(self, request: Request, preset_id: str) -> Response:
        try:
            client = get_ch_client()
            deleted = delete_formula_preset(client, preset_id)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        if not deleted:
            return Response({"detail": "Formula preset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"detail": "Formula preset deleted"}, status=status.HTTP_200_OK)

class FormulaPresetDeleteView(APIView):
    """Soft delete a formula preset (mark as inactive)."""
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def delete(self, request: Request, preset_id: str) -> Response:
        try:
            client = get_ch_client()
            deleted = delete_formula_preset(client, preset_id)
        except Exception as exc:
            return Response({"detail": f"ClickHouse error: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
        if not deleted:
            return Response({"detail": "Formula preset not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"detail": "Formula preset deleted"}, status=status.HTTP_200_OK)


class ScreenIrSchemaView(APIView):
    """Return the JSON schema for the universe_query_v1 IR.

    This endpoint exposes the Pydantic-generated JSON schema for the
    UniverseQueryV1 specification, including the full `where` expression
    tree structure with support for bar offsets (`offset` on column operands).
    """
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        schema = get_universe_ir_schema()
        return Response(schema)
