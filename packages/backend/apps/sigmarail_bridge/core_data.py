"""Authenticated AppTension endpoints for SigmaRail's schema-bound core query API."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib.resources import files
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import clickhouse_connect
from django.conf import settings
from django.utils import timezone
from pydantic import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from sigmarail.query import compile_query, describe_dataset, list_datasets, query_dataset
from sigmarail.universe import compile_universe_spec, universe_membership_by_ticker
from sigmarail_spec.data_query import DataQueryV1

from .views import DomainAPIRouteView, _workspace_for_request


def _use_domain_api_when_native_data_is_disabled(request: Request):
    if settings.SIGMARAIL_CLICKHOUSE_ENABLED:
        return None
    return DomainAPIRouteView()._dispatch(request)


@lru_cache(maxsize=1)
def _clickhouse_client():
    if not settings.SIGMARAIL_CLICKHOUSE_ENABLED:
        raise RuntimeError("The direct SigmaRail ClickHouse query path is disabled.")
    if not settings.SIGMARAIL_CLICKHOUSE_HOST or not settings.SIGMARAIL_CLICKHOUSE_USER:
        raise RuntimeError("SigmaRail ClickHouse host and read-only user must be configured.")

    return clickhouse_connect.get_client(
        host=settings.SIGMARAIL_CLICKHOUSE_HOST,
        port=settings.SIGMARAIL_CLICKHOUSE_HTTP_PORT,
        username=settings.SIGMARAIL_CLICKHOUSE_USER,
        password=settings.SIGMARAIL_CLICKHOUSE_PASSWORD,
        database=settings.SIGMARAIL_CLICKHOUSE_DATABASE,
        secure=settings.SIGMARAIL_CLICKHOUSE_SECURE,
        connect_timeout=10,
        send_receive_timeout=30,
    )


class CoreDatasetsView(APIView):
    """List SQL-generated core datasets without querying ClickHouse."""

    def get(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error
        return Response(list_datasets())


class CoreDatasetView(APIView):
    """Return the SQL-generated field and lineage contract for a core dataset."""

    def get(self, request: Request, dataset_id: str) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error
        try:
            return Response(describe_dataset(dataset_id))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)


class CoreQueryView(APIView):
    """Validate a SigmaRail query contract and execute it using a read-only client."""

    def post(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error

        body: dict[str, Any] = request.data if isinstance(request.data, dict) else {}
        try:
            query = DataQueryV1.model_validate(body)
            compile_query(query)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = _clickhouse_client()
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        result = query_dataset(query, client=client)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST if result.get("code") == "invalid_query" else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)
        return Response(result)


class LatestTradingDateView(APIView):
    """Return the latest available price date through SigmaRail's typed query API."""

    def get(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error

        date_field = "sigmarail.field.screener_price_tech_daily.date.date"
        try:
            query = DataQueryV1.model_validate(
                {
                    "version": 1,
                    "module_id": "sigmarail.core",
                    "dataset_id": "sigmarail.core.screener_price_tech_daily",
                    "select": [{"field_id": date_field, "alias": "latest_date"}],
                    "where": {
                        "op": "lte",
                        "field_id": date_field,
                        "value": timezone.localdate().isoformat(),
                    },
                    "order_by": [{"field_id": date_field, "direction": "desc"}],
                    "limit": 1,
                }
            )
            compile_query(query)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = _clickhouse_client()
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        result = query_dataset(query, client=client)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST if result.get("code") == "invalid_query" else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)

        rows = result.get("rows") or []
        latest = rows[0].get("latest_date") if rows else None
        return Response({"latest_date": latest})


class AsOfDateRangeView(APIView):
    """List recent price-session dates through SigmaRail's typed query API."""

    def get(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error

        try:
            limit = int(request.query_params.get("limit") or 10000)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        limit = min(max(limit, 1), 10000)

        date_field = "sigmarail.field.screener_price_tech_daily.date.date"
        try:
            query = DataQueryV1.model_validate(
                {
                    "version": 1,
                    "module_id": "sigmarail.core",
                    "dataset_id": "sigmarail.core.screener_price_tech_daily",
                    "select": [{"field_id": date_field, "alias": "date"}],
                    "where": {
                        "op": "lte",
                        "field_id": date_field,
                        "value": timezone.localdate().isoformat(),
                    },
                    "order_by": [{"field_id": date_field, "direction": "desc"}],
                    # DataQueryV1's public per-query limit is 1,000. The typed
                    # query API supports a separately bounded total limit for
                    # this date-only listing, matching the existing 10,000 cap.
                    "limit": min(limit, 1000),
                }
            )
            compile_query(query, total_limit=limit)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = _clickhouse_client()
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        result = query_dataset(query, client=client, total_limit=limit)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST if result.get("code") == "invalid_query" else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)

        dates = [str(row["date"]) for row in result.get("rows", []) if row.get("date") is not None]
        return Response({"dates": dates, "count": len(dates)})


_MARKET_CONTEXT_COLUMNS = (
    "date",
    "weekly_allocation_fraction",
    "weekly_allocation_tier",
    "composite_score_normalized",
    "market_regime_signal",
    "is_bear_market_active",
    "allocation_note",
    "breadth_200d",
    "breadth_50d",
    "spy_close",
    "spy_sma200d",
    "spy_sma50d",
    "spy_above200d",
    "spy_above50d",
    "spy_below200d",
    "spy_below200d_3d",
    "ma50_gt_ma200",
    "ma50_slope_pos",
    "ma200_slope_pos",
    "ma_stack_score",
    "risk_on_fast_flags",
    "risk_off_fast_flags",
    "clamp_risk_off",
    "breadth_thrust",
    "ftd",
    "distribution_count_25d",
    "breadth55_days15",
    "is_bear_market_enhanced",
    "bear_severity",
    "bear_market_score",
    "pct_near_52w_high",
    "pct_near_52w_low",
    "pct_above_sma20d",
    "pct_above_sma50d",
    "pct_above_sma200d",
    "pct_above_sma20d_sma5",
    "pct_above_sma50d_sma5",
    "pct_above_sma200d_sma5",
    "price_vs_sma30w_pct",
    "price_vs_sma40w_pct",
    "sma30w_vs_sma40w_pct",
    "sma40w_slope_pct",
    "trend_score",
    "pct_sp500_above_sma40w",
    "pct_stocks_above_sma200",
    "market_sma200_trend_strength",
    "vix_close",
    "vix_sma20d",
    "vix_sma50d",
    "vix_sma200d",
    "vix_vs_sma20d_pct",
    "vix_vs_sma50d_pct",
    "vix_vs_sma200d_pct",
    "vix_contango_proxy",
    "vix_spike_flag",
    "vix_above_sma200d",
    "uvxy_vs_vix_basis",
    "svxy_vs_vix_basis",
)


class MarketContextView(APIView):
    """Read the historical core market-context series through typed dataset fields."""

    def get(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error

        start_date = str(request.query_params.get("start_date") or "").strip()
        end_date = str(request.query_params.get("end_date") or "").strip()
        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required (YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return Response(
                {"detail": "start_date and end_date must be valid YYYY-MM-DD dates"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if start > end:
            return Response(
                {"detail": "start_date must be on or before end_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit") or 2000)
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        limit = min(max(limit, 1), 5000)

        date_field = "sigmarail.field.market_context_daily.date.date"
        try:
            query = DataQueryV1.model_validate(
                {
                    "version": 1,
                    "module_id": "sigmarail.core",
                    "dataset_id": "sigmarail.core.market_context_daily",
                    "select": [
                        {
                            "field_id": f"sigmarail.field.market_context_daily.{column}.{column}",
                            "alias": column,
                        }
                        for column in _MARKET_CONTEXT_COLUMNS
                    ],
                    # market_context_daily has no reviewed as-of declaration;
                    # filter its time field directly instead of using query-level
                    # as-of/date-range semantics reserved for reviewed datasets.
                    "where": {
                        "op": "all",
                        "items": [
                            {"op": "gte", "field_id": date_field, "value": start.isoformat()},
                            {"op": "lte", "field_id": date_field, "value": end.isoformat()},
                        ],
                    },
                    "order_by": [{"field_id": date_field, "direction": "asc"}],
                    # The typed query limit is capped at 1,000; the bounded
                    # total limit preserves the existing endpoint's 5,000 cap.
                    "limit": min(limit, 1000),
                }
            )
            compile_query(query, total_limit=limit)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = _clickhouse_client()
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        result = query_dataset(query, client=client, total_limit=limit)
        if "error" in result:
            response_status = (
                status.HTTP_400_BAD_REQUEST if result.get("code") == "invalid_query" else status.HTTP_502_BAD_GATEWAY
            )
            return Response(result, status=response_status)
        rows = result.get("rows") or []
        return Response([{key: _preview_json_value(value) for key, value in row.items()} for row in rows])


def _preview_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        try:
            value = float(value)
        except (OverflowError, ValueError):
            return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if not isinstance(value, (str, int, float, bool, list, tuple, dict)):
        item = getattr(value, "item", None)
        if callable(item):
            return _preview_json_value(item())
        return str(value)
    return value


def _shape_universe_preview(rows: list[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    shaped = []
    for source in rows:
        row = {
            "ticker": str(source.get("ticker") or "").upper(),
            "date": str(source.get("date") or as_of),
            "close": source.get("closeadj") if source.get("closeadj") is not None else source.get("close"),
            "rs_rating": source.get("rs_rating"),
            "technical_rating": source.get("technical_rating"),
            "setup_quality_rating": source.get("setup_quality_rating"),
            "high_growth_momentum_rating": source.get("high_growth_momentum_rating"),
            "avg_vol_50d": source.get("avg_vol_50d"),
            "overall_score": source.get("overall_score"),
            "minervini_score": source.get("minervini_score"),
            "oneil_score": source.get("oneil_score"),
            "classification": source.get("classification"),
            "industry_group_rank": source.get("industry_group_rank"),
        }
        core = set(row) | {"closeadj"}
        row.update({key: value for key, value in source.items() if key not in core})
        shaped.append({key: _preview_json_value(value) for key, value in row.items()})
    return shaped


class UniversePreviewView(APIView):
    """Execute compatible universe previews through SigmaRail Core in AppTension."""

    def post(self, request: Request) -> Response:
        fallback = _use_domain_api_when_native_data_is_disabled(request)
        if fallback is not None:
            return fallback
        _, error = _workspace_for_request(request)
        if error:
            return error

        body = request.data if isinstance(request.data, dict) else {}
        as_of = str(body.get("as_of") or "").strip()[:10]
        if not as_of:
            return Response({"detail": "as_of is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError:
            return Response({"detail": "as_of must be an ISO date"}, status=status.HTTP_400_BAD_REQUEST)
        spec = body.get("spec")
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)

        # Request exchange with the preview so this route does not need a
        # second lookup. The compiler rejects fields outside its installed
        # contract; those specs continue through the compatibility service.
        native_spec = dict(spec)
        select = spec.get("select")
        if isinstance(select, list) and all(isinstance(item, str) for item in select):
            native_spec["select"] = list(dict.fromkeys([*select, "exchange"]))
        try:
            sql, params = compile_universe_spec(
                native_spec,
                start_date=as_of_date.isoformat(),
                end_date=as_of_date.isoformat(),
            )
        except (ValidationError, ValueError, TypeError):
            return DomainAPIRouteView()._dispatch(request)

        try:
            client = _clickhouse_client()
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            result = client.query(sql, parameters=params)
            result_date = as_of
            raw_rows = [
                {name: _preview_json_value(value) for name, value in zip(result.column_names, values, strict=True)}
                for values in result.result_rows
            ]

            # Fall back only when the requested session has no source data.
            # A valid session with zero matches is a real empty universe and
            # must not silently show membership from a prior date.
            if not raw_rows:
                session_data = client.query(
                    "SELECT 1 FROM screener_price_tech_daily WHERE date = {as_of:Date} LIMIT 1",
                    parameters={"as_of": as_of},
                )
                has_session_data = bool(getattr(session_data, "result_rows", []))
                if not has_session_data:
                    latest = client.query(
                        "SELECT max(date) FROM screener_price_tech_daily WHERE date < {as_of:Date}",
                        parameters={"as_of": as_of},
                    )
                    latest_rows = getattr(latest, "result_rows", [])
                    fallback_date = str(latest_rows[0][0])[:10] if latest_rows and latest_rows[0][0] else None
                    if fallback_date and fallback_date != as_of:
                        sql, params = compile_universe_spec(
                            native_spec,
                            start_date=fallback_date,
                            end_date=fallback_date,
                        )
                        result = client.query(sql, parameters=params)
                        result_date = fallback_date
                        raw_rows = [
                            {name: _preview_json_value(value) for name, value in zip(result.column_names, values, strict=True)}
                            for values in result.result_rows
                        ]
        except Exception:
            return Response(
                {"detail": "SigmaRail ClickHouse query failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        rows = _shape_universe_preview(raw_rows, result_date)
        if body.get("include_tenure") and rows:
            tenure_start = str(body.get("tenure_start") or body.get("start_date") or "").strip()
            if not tenure_start:
                tenure_start = (date.fromisoformat(result_date) - timedelta(days=int(252 * 1.45))).isoformat()
            tickers = [row["ticker"] for row in rows if row.get("ticker")]
            try:
                tenure = universe_membership_by_ticker(
                    spec,
                    start_date=tenure_start,
                    end_date=result_date,
                    tickers=tickers or None,
                    client=client,
                )
                for row in rows:
                    row["days_in_universe"] = int(tenure.get(row["ticker"], 0))
            except Exception:
                for row in rows:
                    row["days_in_universe"] = None

        return Response(
            {
                "as_of": result_date,
                **({"as_of_requested": as_of, "as_of_fallback": result_date} if result_date != as_of else {}),
                "count": len(rows),
                "rows": rows,
                "screen_ir": "universe_query_v1",
                "spec": spec,
                "sql": sql.strip(),
                "params": {key: params[key] for key in sorted(params)},
                "limit": int(spec.get("limit_per_day", 500)),
            }
        )


class UniverseCompileSqlView(APIView):
    """Compile the versioned universe spec without opening a ClickHouse connection."""

    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error

        body: dict[str, Any] = request.data if isinstance(request.data, dict) else {}
        spec = body.get("spec")
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sql, params = compile_universe_spec(spec)
        except Exception as exc:
            return Response(
                {"detail": f"failed to compile SigmaRail universe query: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"sql": sql.strip(), "params": {key: params[key] for key in sorted(params)}})


class UniverseSchemaView(APIView):
    """Serve the versioned universe-query schema packaged with SigmaRail Spec."""

    def get(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error

        path = files("sigmarail_spec").joinpath("data", "strategy", "universe-query.json")
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return Response(
                {"detail": f"SigmaRail universe schema is unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(schema)
