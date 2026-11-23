"""Tenant-authorized GraphQL reads for the SigmaRail MCP tools."""

from __future__ import annotations

from datetime import date, datetime, timezone as datetime_timezone
import json
import logging
from importlib.resources import files

import graphene
from graphene.types.generic import GenericScalar
from django.conf import settings
from django.utils import timezone
from graphql_relay import from_global_id, to_global_id
from rest_framework.exceptions import ValidationError

from apps.multitenancy.middleware import get_current_tenant_with_membership_check
from .core_data import _clickhouse_client, _preview_json_value

logger = logging.getLogger(__name__)


def _authorize_tenant(info, tenant_id):
    """Require an authenticated user with accepted membership in tenant_id."""
    user = getattr(info.context, "user", None)
    if user is None or not user.is_authenticated:
        raise ValidationError("Authentication is required.")

    raw_tenant_id = tenant_id
    try:
        type_name, decoded_id = from_global_id(tenant_id)
        if type_name == "TenantType":
            raw_tenant_id = decoded_id
    except (TypeError, ValueError):
        pass

    tenant = get_current_tenant_with_membership_check(
        raw_tenant_id, user, getattr(info.context, "_request", info.context)
    )
    if tenant is None:
        raise ValidationError("You are not a member of this tenant.")
    return tenant


def _json_object(value, name):
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be a JSON object.")
    return value


class SigmaRailStockSnapshot(graphene.ObjectType):
    ticker = graphene.String(required=True)
    as_of_date = graphene.String()
    requested_as_of_date = graphene.String()
    availability_status = graphene.String(required=True)
    latest_available_date = graphene.String()
    company_name = graphene.String()
    sector = graphene.String()
    industry = graphene.String()
    close = graphene.Float()
    rs_rating = graphene.Float()
    atr_14_pct = graphene.Float()
    stage_code = graphene.String()
    sma50d = graphene.Float()
    sma200d = graphene.Float()


class Query(graphene.ObjectType):
    sigmarail_readiness = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description=(
            "Check authenticated tenant access, effective permission codes, and read-only ClickHouse "
            "coverage for the latest price and market-context sessions. Returns actionable status codes; "
            "an unavailable dataset is never represented as a zero-valued market result."
        ),
    )
    sigmarail_core_datasets = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List schema-registered SigmaRail datasets, grains, time semantics, and lineage roots.",
    )
    sigmarail_core_dataset = GenericScalar(
        dataset_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Describe one registered dataset and its stable selectable field IDs.",
    )
    sigmarail_core_query_schema = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="Return the canonical DataQueryV1 JSON schema for authoring bounded queries.",
    )
    sigmarail_core_query = GenericScalar(
        query=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description=(
            "Execute a bounded read-only DataQueryV1 AST. The query's select list determines "
            "the returned row fields; field IDs, joins, expressions, date bounds, and limits "
            "are validated against SigmaRail's canonical schema."
        ),
    )
    sigmarail_strategy_pipeline_schema = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="Return the canonical SigmaRail PipelineDocument JSON schema for strategy authoring.",
    )
    sigmarail_strategy_validate_pipeline = GenericScalar(
        pipeline=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Validate a versioned SigmaRail PipelineDocument AST using the canonical strategy package.",
    )
    sigmarail_strategy_compile_pipeline = GenericScalar(
        pipeline=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compile a validated SigmaRail PipelineDocument into the LEAN-compatible runtime spec.",
    )
    sigmarail_screen_schema = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="Return the canonical UniverseQueryV1 schema used to author screener ASTs.",
    )
    sigmarail_screen_compile = GenericScalar(
        spec=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compile a canonical UniverseQueryV1 AST into parameterized SigmaRail SQL without executing it.",
    )
    sigmarail_screen_preview = GenericScalar(
        spec=GenericScalar(required=True),
        as_of=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description=(
            "Run a bounded point-in-time UniverseQueryV1 screen. Returned row fields follow the AST select list."
        ),
    )
    sigmarail_screen_sector_range = GenericScalar(
        spec=GenericScalar(required=True),
        start_date=graphene.String(required=True),
        end_date=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Summarize point-in-time universe membership by sector over a bounded date range.",
    )
    sigmarail_screen_presets = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List supported named screen presets backed by the canonical SigmaRail universe templates.",
    )
    sigmarail_screen_preset_preview = GenericScalar(
        as_of=graphene.String(required=True),
        limit=graphene.Int(),
        preset=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="Run one named point-in-time SigmaRail screener preset.",
    )
    sigmarail_screen_probe = GenericScalar(
        input=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description=(
            "Inspect canonical screener AST stage prefixes using the bounded layers, asof, range, or diff probe."
        ),
    )
    sigmarail_catalog_tables = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List schema-registered SigmaRail datasets and declared join relationships.",
    )
    sigmarail_catalog_columns = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List registered SigmaRail fields with stable IDs, owners, physical columns, and types.",
    )
    sigmarail_catalog_join_paths = GenericScalar(
        from_entity=graphene.String(),
        to_entity=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="List declared SigmaRail join relationships, optionally filtered by source and destination.",
    )
    sigmarail_catalog_entity = GenericScalar(
        entity=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Describe one SigmaRail dataset by stable ID or physical table name.",
    )
    sigmarail_strategy_factors = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List canonical semantic strategy factors and their field mappings.",
    )
    sigmarail_strategy_presets = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List canonical built-in SigmaRail strategy presets.",
    )
    sigmarail_templates = GenericScalar(
        kind=graphene.String(),
        status=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="List installed screener and strategy templates from the canonical SigmaRail catalog.",
    )
    sigmarail_template = GenericScalar(
        template_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Load one installed screener or strategy template, including its canonical AST body.",
    )
    sigmarail_strategy_compile_preset = GenericScalar(
        preset_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compile a named canonical strategy preset to its LEAN-compatible spec.",
    )
    sigmarail_strategy_decompile_pipeline = GenericScalar(
        spec=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Decompile a LEAN-compatible strategy spec into its editable canonical PipelineDocument AST.",
    )
    sigmarail_strategy_portfolio_schema = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="Return the canonical PortfolioDocument schema for portfolio strategy authoring.",
    )
    sigmarail_strategy_compile_portfolio = GenericScalar(
        portfolio=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compile a canonical PortfolioDocument AST into a LEAN-compatible strategy spec.",
    )
    sigmarail_strategy_decompile_portfolio = GenericScalar(
        spec=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Decompile a LEAN-compatible portfolio spec into an editable PortfolioDocument AST.",
    )
    sigmarail_strategy_setup_recipes = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List canonical setup recipe packs used to compose strategy PipelineDocuments.",
    )
    sigmarail_strategy_compose_document = GenericScalar(
        preset_id=graphene.String(),
        setup_recipe_ids=graphene.List(graphene.String),
        tenant_id=graphene.ID(required=True),
        description="Compose a canonical PipelineDocument from a strategy preset and setup recipe IDs.",
    )
    sigmarail_strategy_position_fields = GenericScalar(
        tenant_id=graphene.ID(required=True),
        description="List canonical position-field bindings available to strategy expressions.",
    )
    sigmarail_strategy_diff = GenericScalar(
        spec_a=GenericScalar(required=True),
        spec_b=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Return a semantic slot-level diff between two canonical pipeline or compiled strategy specs.",
    )
    sigmarail_strategy_lint = GenericScalar(
        pipeline=GenericScalar(required=True),
        tenant_id=graphene.ID(required=True),
        description="Validate a PipelineDocument and report runtime-contract errors and warnings.",
    )
    sigmarail_strategy_saved_specs = GenericScalar(
        limit=graphene.Int(),
        search=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="List strategies saved in the active tenant, limited to records visible to the signed-in user.",
    )
    sigmarail_strategy_saved_spec = GenericScalar(
        ir_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Load one tenant-owned or shared strategy record with its canonical AST and lineage.",
    )
    sigmarail_backtest_jobs = GenericScalar(
        limit=graphene.Int(),
        status=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="List AppTension-owned backtest jobs for the active tenant.",
    )
    sigmarail_backtest_job = GenericScalar(
        job_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Read one tenant-owned backtest job and its progress snapshot.",
    )
    sigmarail_backtest_runs = GenericScalar(
        ir_id=graphene.String(),
        limit=graphene.Int(),
        tenant_id=graphene.ID(required=True),
        description="List tenant-owned backtest runs and their stored result summaries.",
    )
    sigmarail_backtest_report = GenericScalar(
        run_id=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Read the analytical report for a backtest run owned by the active tenant.",
    )
    sigmarail_backtest_compare = GenericScalar(
        run_id_a=graphene.String(required=True),
        run_id_b=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compare two tenant-owned backtest reports and their principal performance metrics.",
    )
    sigmarail_market_regime = GenericScalar(
        as_of_date=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Read the market-regime and allocation context for one session date.",
    )
    sigmarail_regime_allocation = GenericScalar(
        as_of_date=graphene.String(required=True),
        policy_name=graphene.String(),
        ticker=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description="Explain the regime allocation for a ticker and session date, optionally for a named policy.",
    )
    sigmarail_regime_compare_periods = GenericScalar(
        focus_start=graphene.String(required=True),
        focus_end=graphene.String(required=True),
        reference_start=graphene.String(required=True),
        reference_end=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Compare market breadth and regime allocation aggregates across two date windows.",
    )
    sigmarail_regime_entry_gate = GenericScalar(
        as_of_date=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        description="Evaluate the daily market entry gate from the canonical SigmaRail rule set.",
    )
    sigmarail_regime_transition_weight = GenericScalar(
        as_of_date=graphene.String(required=True),
        base_weight=graphene.Float(),
        tenant_id=graphene.ID(required=True),
        description="Compute the market-regime transition weight for a session date and base weight.",
    )
    sigmarail_regime_rank_candidates = GenericScalar(
        as_of_date=graphene.String(required=True),
        passing_tickers=graphene.List(graphene.String, required=True),
        tenant_id=graphene.ID(required=True),
        description="Rank a supplied list of already-passing tickers using SigmaRail regime and alpha context.",
    )

    sigmarail_stock_snapshot = graphene.Field(
        SigmaRailStockSnapshot,
        ticker=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        as_of_date=graphene.String(),
        description=(
            "Read the latest or point-in-time price, trend, and relative-strength snapshot "
            "for one stock from SigmaRail's read-only daily dataset. The result reports its "
            "actual asOfDate, requestedAsOfDate, availabilityStatus, and latestAvailableDate; "
            "historical requests may resolve to the latest prior available session."
        ),
    )

    @staticmethod
    def resolve_sigmarail_readiness(root, info, tenant_id):
        tenant = _authorize_tenant(info, tenant_id)
        user = info.context.user
        from apps.multitenancy.models import get_user_permissions_for_tenant

        checked_at = datetime.now(datetime_timezone.utc).isoformat()
        try:
            permission_codes = sorted(get_user_permissions_for_tenant(user, tenant))
        except Exception:
            logger.exception("SigmaRail readiness permission lookup failed")
            permission_codes = []
            permission_status = {
                "status": "unavailable",
                "code": "PERMISSIONS_UNAVAILABLE",
                "action": "Retry this check; do not infer access to protected actions.",
            }
        else:
            permission_status = {"status": "available", "code": None}

        readiness = {
            "checked_at": checked_at,
            "tenant_id": str(tenant.pk),
            "overall_status": "ready",
            "authentication": {"status": "authenticated", "code": None},
            "permissions": {**permission_status, "codes": permission_codes},
            "data": [],
        }
        if not settings.SIGMARAIL_CLICKHOUSE_ENABLED:
            readiness["overall_status"] = "degraded"
            readiness["data"] = [
                {
                    "dataset_id": dataset_id,
                    "status": "unavailable",
                    "code": "DATA_BACKEND_DISABLED",
                    "action": "Enable SigmaRail's native read-only ClickHouse path before using data tools.",
                }
                for dataset_id in (
                    "sigmarail.core.screener_price_tech_daily",
                    "sigmarail.core.market_context_daily",
                )
            ]
            return readiness

        client = None
        try:
            from .core_data import _clickhouse_client

            client = _clickhouse_client()
            datasets = (
                ("sigmarail.core.screener_price_tech_daily", "screener_price_tech_daily", True),
                ("sigmarail.core.market_context_daily", "market_context_daily", False),
            )
            for dataset_id, table_name, has_ticker in datasets:
                latest_result = client.query(f"SELECT max(date) FROM {table_name}")
                latest_date = latest_result.result_rows[0][0] if latest_result.result_rows else None
                if latest_date is None or str(latest_date) in {"1970-01-01", "0000-00-00"}:
                    readiness["data"].append(
                        {
                            "dataset_id": dataset_id,
                            "status": "unavailable",
                            "latest_available_date": None,
                            "row_count": 0,
                            "symbol_count": 0 if has_ticker else None,
                            "code": "DATA_NOT_AVAILABLE",
                            "action": (
                                "Check the loader/populate run and source coverage; "
                                "do not treat missing data as zero."
                            ),
                        }
                    )
                    readiness["overall_status"] = "degraded"
                    continue

                if has_ticker:
                    coverage_result = client.query(
                        "SELECT count(), uniqExact(ticker) "
                        "FROM screener_price_tech_daily FINAL WHERE date = {latest:Date}",
                        parameters={"latest": latest_date},
                    )
                else:
                    coverage_result = client.query(
                        "SELECT count() FROM market_context_daily FINAL WHERE date = {latest:Date}",
                        parameters={"latest": latest_date},
                    )
                counts = coverage_result.result_rows[0] if coverage_result.result_rows else (
                    (0, 0) if has_ticker else (0,)
                )
                row_count = int(counts[0] or 0)
                symbol_count = int(counts[1] or 0) if has_ticker else None
                readiness["data"].append(
                    {
                        "dataset_id": dataset_id,
                        "status": "available" if row_count else "unavailable",
                        "latest_available_date": str(latest_date),
                        "calendar_days_old": max((timezone.localdate() - date.fromisoformat(str(latest_date))).days, 0),
                        "row_count": row_count,
                        "symbol_count": symbol_count,
                        "code": None if row_count else "DATA_NOT_AVAILABLE",
                        "action": None if row_count else (
                            "Check population for the reported date; "
                            "do not infer a zero-valued result."
                        ),
                    }
                )
                if not row_count:
                    readiness["overall_status"] = "degraded"
        except Exception:
            logger.exception("SigmaRail readiness data probe failed")
            readiness["overall_status"] = "degraded"
            readiness["data_error"] = {
                "status": "unavailable",
                "code": "DATA_SOURCE_UNAVAILABLE",
                "action": (
                    "Retry later or inspect backend and ClickHouse health; "
                    "do not interpret missing results as zero."
                ),
            }
        finally:
            if client is not None:
                client.close()
        if permission_status["status"] != "available":
            readiness["overall_status"] = "degraded"
        return readiness

    @staticmethod
    def resolve_sigmarail_core_datasets(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import list_datasets

        return list_datasets()

    @staticmethod
    def resolve_sigmarail_core_dataset(root, info, dataset_id, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import describe_dataset

        try:
            return describe_dataset(dataset_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    @staticmethod
    def resolve_sigmarail_core_query_schema(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.data_query import DataQueryV1

        return DataQueryV1.model_json_schema()

    @staticmethod
    def resolve_sigmarail_core_query(root, info, query, tenant_id):
        _authorize_tenant(info, tenant_id)
        query_data = _json_object(query, "query")

        from pydantic import ValidationError as PydanticValidationError
        from sigmarail.query import compile_query, query_dataset
        from sigmarail_spec.data_query import DataQueryV1

        try:
            parsed_query = DataQueryV1.model_validate(query_data)
            # Validate dataset IDs, field IDs, joins, AST bounds, and SQL compilation
            # before opening a ClickHouse connection.
            compile_query(parsed_query)
        except (PydanticValidationError, ValueError) as exc:
            return {
                "error": str(exc),
                "code": "invalid_query",
                "error_code": "INVALID_SPEC",
                "action": "Correct the DataQueryV1 fields using sigmarail_core_query_schema, then retry.",
            }
        try:
            client = _clickhouse_client()
        except Exception:
            logger.exception("SigmaRail ClickHouse client initialization failed")
            return {
                "error": "The SigmaRail data service is unavailable.",
                "code": "query_failed",
                "error_code": "DATA_SOURCE_UNAVAILABLE",
                "action": "Call sigmarail_readiness and retry only after the data service is available.",
            }
        try:
            return query_dataset(parsed_query, client=client)
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_strategy_pipeline_schema(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy import PipelineDocument

        return PipelineDocument.model_json_schema()

    @staticmethod
    def resolve_sigmarail_strategy_validate_pipeline(root, info, pipeline, tenant_id):
        _authorize_tenant(info, tenant_id)
        pipeline_data = _json_object(pipeline, "pipeline")

        from sigmarail_spec.strategy import PipelineDocument, compile_pipeline

        try:
            document = PipelineDocument.model_validate(pipeline_data)
            compile_pipeline(document)
            return {"valid": True}
        except Exception as exc:  # Pydantic/spec compiler can raise validation or semantic errors.
            return {"valid": False, "code": "validation_failed", "error": str(exc)}

    @staticmethod
    def resolve_sigmarail_strategy_compile_pipeline(root, info, pipeline, tenant_id):
        _authorize_tenant(info, tenant_id)
        pipeline_data = _json_object(pipeline, "pipeline")

        from sigmarail_spec.strategy import PipelineDocument, compile_pipeline

        try:
            document = PipelineDocument.model_validate(pipeline_data)
            compiled = compile_pipeline(document)
            from screens.risk_rules import materialize_swing_risk_rules

            materialize_swing_risk_rules(compiled)
            return compiled
        except Exception as exc:  # Match the AppTension strategy compile endpoint contract.
            return {"error": str(exc), "code": "compile_failed"}

    @staticmethod
    def resolve_sigmarail_screen_schema(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        try:
            return json.loads(
                files("sigmarail_spec").joinpath("data", "strategy", "universe-query.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError("SigmaRail UniverseQueryV1 schema is unavailable.") from exc

    @staticmethod
    def resolve_sigmarail_screen_compile(root, info, spec, tenant_id):
        _authorize_tenant(info, tenant_id)
        spec_data = _json_object(spec, "spec")
        from sigmarail.universe import compile_universe_spec

        try:
            sql, params = compile_universe_spec(spec_data)
            return {"sql": sql.strip(), "params": {key: params[key] for key in sorted(params)}}
        except Exception as exc:
            return {"error": str(exc), "code": "invalid_universe_query"}

    @staticmethod
    def resolve_sigmarail_screen_preview(root, info, spec, as_of, tenant_id):
        _authorize_tenant(info, tenant_id)
        spec_data = _json_object(spec, "spec")
        try:
            as_of_date = date.fromisoformat(str(as_of))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOf must be an ISO date (YYYY-MM-DD).") from exc

        from sigmarail.universe import compile_universe_spec

        try:
            sql, params = compile_universe_spec(
                spec_data,
                start_date=as_of_date.isoformat(),
                end_date=as_of_date.isoformat(),
            )
        except Exception as exc:
            return {"error": str(exc), "code": "invalid_universe_query"}

        client = _clickhouse_client()
        try:
            result = client.query(sql, parameters=params)
            rows = [
                {name: _preview_json_value(value) for name, value in zip(result.column_names, values, strict=True)}
                for values in result.result_rows
            ]
            return {
                "as_of": as_of_date.isoformat(),
                "count": len(rows),
                "rows": rows,
                "screen_ir": "universe_query_v1",
                "spec": spec_data,
            }
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_screen_sector_range(root, info, spec, start_date, end_date, tenant_id):
        _authorize_tenant(info, tenant_id)
        spec_data = _json_object(spec, "spec")
        try:
            start = date.fromisoformat(str(start_date))
            end = date.fromisoformat(str(end_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("startDate and endDate must be ISO dates (YYYY-MM-DD).") from exc
        if start > end:
            raise ValidationError("startDate must be on or before endDate.")

        from sigmarail.universe import universe_membership_sector_counts

        client = _clickhouse_client()
        try:
            sector_counts = universe_membership_sector_counts(
                spec_data,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                client=client,
            )
        finally:
            client.close()
        totals: dict[str, int] = {}
        for row in sector_counts:
            day = str(row["date"])
            totals[day] = totals.get(day, 0) + int(row["count"])
        counts = list(totals.values())
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "dates": sorted(totals),
            "member_counts": [totals[day] for day in sorted(totals)],
            "sector_counts": sector_counts,
            "summary": {
                "trading_days": len(counts),
                "avg_members_per_day": round(sum(counts) / len(counts), 2) if counts else 0.0,
                "min_members_per_day": min(counts) if counts else 0,
                "max_members_per_day": max(counts) if counts else 0,
            },
        }

    @staticmethod
    def resolve_sigmarail_screen_presets(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from screens.adapter import list_screen_presets

        return {"presets": list_screen_presets()}

    @staticmethod
    def resolve_sigmarail_screen_preset_preview(root, info, as_of, tenant_id, limit=50, preset="leaders"):
        _authorize_tenant(info, tenant_id)
        try:
            as_of_date = date.fromisoformat(str(as_of))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOf must be an ISO date (YYYY-MM-DD).") from exc
        from screens.adapter import preview_screen

        client = _clickhouse_client()
        try:
            return preview_screen(
                client,
                as_of=as_of_date.isoformat(),
                preset=preset or "leaders",
                limit=min(max(int(limit or 50), 1), 100),
            )
        except ValueError as exc:
            return {"error": str(exc), "code": "invalid_screen_preset"}
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_screen_probe(root, info, input, tenant_id):
        _authorize_tenant(info, tenant_id)
        body = _json_object(input, "input")
        view = str(body.get("view") or "layers").strip().lower()
        from screens.probe import run_probe

        if view == "layers":
            try:
                return run_probe(body)
            except ValueError as exc:
                return {"error": str(exc), "code": "invalid_screen_probe"}
        client = _clickhouse_client()
        try:
            return run_probe(body, client=client)
        except ValueError as exc:
            return {"error": str(exc), "code": "invalid_screen_probe"}
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_catalog_tables(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import _module_manifest

        manifest = _module_manifest()
        return {
            "spine": "screener_price_tech_daily",
            "join_type": "declared_relationships",
            "tables": manifest["datasets"],
            "joins": manifest["joins"],
        }

    @staticmethod
    def resolve_sigmarail_catalog_columns(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import _column_index, _datasets

        datasets = _datasets()
        columns = {}
        candidates = {}
        for field_id, (dataset_id, physical, meta) in sorted(_column_index().items()):
            candidates.setdefault(str(meta["name"]), []).append((field_id, dataset_id, physical, meta))
        for name, choices in candidates.items():
            field_id, dataset_id, physical, meta = next(
                (row for row in choices if row[1] == "sigmarail.core.screener_price_tech_daily"),
                choices[0],
            )
            columns[name] = {
                "id": field_id,
                "dataset_id": dataset_id,
                "physical": physical,
                "table": datasets[dataset_id]["table"],
                "type": meta.get("type"),
                "description": meta.get("comment", ""),
            }
        return {"count": len(columns), "columns": columns}

    @staticmethod
    def resolve_sigmarail_catalog_join_paths(root, info, tenant_id, from_entity=None, to_entity=None):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import _module_manifest

        joins = list(_module_manifest()["joins"])
        if from_entity:
            joins = [row for row in joins if row["from_dataset"] == from_entity.strip()]
        if to_entity:
            joins = [row for row in joins if row["to_dataset"] == to_entity.strip()]
        return {"relationships": joins}

    @staticmethod
    def resolve_sigmarail_catalog_entity(root, info, entity, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.query import _core_tables, _datasets

        name = (entity or "").strip()
        datasets = _datasets()
        dataset = datasets.get(name)
        if dataset is None:
            dataset = next((row for row in datasets.values() if row["table"] == name), None)
        if dataset is None:
            return {"error": f"unknown SigmaRail core dataset {entity!r}", "code": "unknown_dataset"}
        tables = _core_tables()
        return {"entity": dataset["dataset_id"], "meta": {**dataset, "schema": tables[dataset["table"]]}}

    @staticmethod
    def resolve_sigmarail_strategy_factors(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy import list_factors

        return {"factors": list_factors()}

    @staticmethod
    def resolve_sigmarail_strategy_presets(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy.presets import list_presets

        return {"presets": list_presets()}

    @staticmethod
    def resolve_sigmarail_templates(root, info, tenant_id, kind=None, status=None):
        _authorize_tenant(info, tenant_id)
        from sigmarail.features.template_catalog import list_templates, summary_row

        if kind not in (None, "screener", "strategy"):
            raise ValidationError("kind must be screener or strategy.")
        if status not in (None, "active", "deprecated", "draft"):
            raise ValidationError("status must be active, deprecated, or draft.")
        return {"templates": [summary_row(row) for row in list_templates(kind=kind, status=status)]}

    @staticmethod
    def resolve_sigmarail_template(root, info, template_id, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail.features.template_catalog import get_template

        try:
            return get_template(template_id)
        except ValueError as exc:
            return {"error": str(exc), "code": "unknown_template"}

    @staticmethod
    def resolve_sigmarail_strategy_compile_preset(root, info, preset_id, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy import compile_pipeline
        from sigmarail_spec.strategy.presets import get_preset

        try:
            compiled = compile_pipeline(get_preset(preset_id))
            from screens.risk_rules import materialize_swing_risk_rules

            materialize_swing_risk_rules(compiled)
            return compiled
        except Exception as exc:
            return {"error": str(exc), "code": "compile_failed"}

    @staticmethod
    def resolve_sigmarail_strategy_decompile_pipeline(root, info, spec, tenant_id):
        _authorize_tenant(info, tenant_id)
        spec_data = _json_object(spec, "spec")
        from sigmarail_spec.strategy import decompile_pipeline

        try:
            return {"pipeline": decompile_pipeline(spec_data).model_dump(mode="json")}
        except Exception as exc:
            return {"error": str(exc), "code": "decompile_failed"}

    @staticmethod
    def resolve_sigmarail_strategy_portfolio_schema(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy import PortfolioDocument

        return PortfolioDocument.model_json_schema()

    @staticmethod
    def resolve_sigmarail_strategy_compile_portfolio(root, info, portfolio, tenant_id):
        _authorize_tenant(info, tenant_id)
        portfolio_data = _json_object(portfolio, "portfolio")
        from sigmarail_spec.strategy import PortfolioDocument, compile_portfolio

        try:
            return {"spec": compile_portfolio(PortfolioDocument.model_validate(portfolio_data))}
        except Exception as exc:
            return {"error": str(exc), "code": "compile_failed"}

    @staticmethod
    def resolve_sigmarail_strategy_decompile_portfolio(root, info, spec, tenant_id):
        _authorize_tenant(info, tenant_id)
        spec_data = _json_object(spec, "spec")
        from sigmarail_spec.strategy import decompile_portfolio

        try:
            return {"portfolio": decompile_portfolio(spec_data).model_dump(mode="json")}
        except Exception as exc:
            return {"error": str(exc), "code": "decompile_failed"}

    @staticmethod
    def resolve_sigmarail_strategy_setup_recipes(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy.setup_recipes import list_setup_recipes

        return {"setup_recipes": list_setup_recipes()}

    @staticmethod
    def resolve_sigmarail_strategy_compose_document(root, info, tenant_id, preset_id=None, setup_recipe_ids=None):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy.presets import get_preset
        from sigmarail_spec.strategy.setup_recipes import apply_setup_recipe, list_setup_recipes

        preset_id = preset_id or "minervini_sepa"
        try:
            document = get_preset(preset_id)
        except ValueError as exc:
            return {"error": str(exc), "code": "unknown_preset"}
        recipes = setup_recipe_ids or ["champion_setup_or"]
        known = {row["id"] for row in list_setup_recipes()}
        for index, recipe_id in enumerate(recipes):
            if recipe_id not in known:
                return {"error": f"Unknown setup recipe {recipe_id!r}.", "code": "unknown_recipe"}
            document = apply_setup_recipe(document, recipe_id, replace=index == 0)
        return {"pipeline": document.model_dump(mode="json")}

    @staticmethod
    def resolve_sigmarail_strategy_position_fields(root, info, tenant_id):
        _authorize_tenant(info, tenant_id)
        from sigmarail_spec.strategy.position_bindings import POSITION_BINDINGS

        fields = [dict(binding) for binding in POSITION_BINDINGS]
        return {"fields": fields, "count": len(fields)}

    @staticmethod
    def resolve_sigmarail_strategy_diff(root, info, spec_a, spec_b, tenant_id):
        _authorize_tenant(info, tenant_id)
        a_data = _json_object(spec_a, "specA")
        b_data = _json_object(spec_b, "specB")
        from sigmarail_spec.strategy import PipelineDocument, decompile_pipeline

        def to_document(data, label):
            if "Framework" in data:
                return decompile_pipeline(data).model_dump(mode="json")
            return PipelineDocument.model_validate(data).model_dump(mode="json")

        try:
            a = to_document(a_data, "specA")
            b = to_document(b_data, "specB")
        except Exception as exc:
            return {"error": str(exc), "code": "invalid_strategy_spec"}
        slots = ("stages", "bindings", "universe", "sizing", "risk", "execution")
        diffs = [
            {"slot": key, "from": a.get(key), "to": b.get(key)}
            for key in slots if a.get(key) != b.get(key)
        ]
        return {"has_diff": bool(diffs), "diffs": diffs}

    @staticmethod
    def resolve_sigmarail_strategy_lint(root, info, pipeline, tenant_id):
        _authorize_tenant(info, tenant_id)
        pipeline_data = _json_object(pipeline, "pipeline")
        from sigmarail_spec.strategy import PipelineDocument

        try:
            document = PipelineDocument.model_validate(pipeline_data)
        except Exception as exc:
            return {"valid": False, "code": "validation_failed", "diagnostics": [{"message": str(exc), "severity": "error"}]}
        diagnostics = []
        bindings = document.model_dump().get("bindings") or {}
        if bindings.get("pcm_scale") and bindings.get("alpha_confidence"):
            diagnostics.append({
                "message": "bindings.pcm_scale conflicts with bindings.alpha_confidence (runtime XOR: scale expression takes precedence; confidence is ignored)",
                "severity": "error",
                "slot": "portfolio_construction",
            })
        allow = bindings.get("risk_allow_pyramid_add") or {}
        if allow and any(token in json.dumps(allow).lower() for token in ("insight", "confidence")):
            diagnostics.append({
                "message": "bindings.risk_allow_pyramid_add references insight/confidence tags, but SwingProgressiveRiskManagementModel ignores them at runtime",
                "severity": "warning",
                "slot": "risk_management",
            })
        return {"valid": not any(row["severity"] == "error" for row in diagnostics), "diagnostics": diagnostics}

    @staticmethod
    def resolve_sigmarail_strategy_saved_specs(root, info, tenant_id, limit=50, search=None):
        tenant = _authorize_tenant(info, tenant_id)
        from django.db.models import Q
        from .models import WorkspaceStrategyReference

        rows = WorkspaceStrategyReference.objects.filter(tenant=tenant).filter(
            Q(owner_user=info.context.user) | Q(is_shared=True) | Q(is_template=True)
        ).exclude(spec__isnull=True).order_by("-updated_at", "ir_id")
        if search:
            term = str(search).strip()[:120]
            rows = rows.filter(Q(ir_id__icontains=term) | Q(title__icontains=term) | Q(notes__icontains=term))
        bounded_limit = min(max(int(limit or 50), 1), 200)
        specs = [
            {
                "ir_id": row.ir_id,
                "title": row.title or row.ir_id,
                "spec_schema_version": row.spec_schema_version or 1,
                "notes": row.notes,
                "category": row.category,
                "is_template": row.is_template,
                "has_pipeline": bool(row.pipeline_document),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "ir_content_hash": row.content_hash,
                "compiler_version": row.compiler_version,
                "lineage": {
                    "parent_ir_id": row.parent_ir_id or None,
                    "parent_content_hash": row.parent_content_hash or None,
                    "mutation_type": row.mutation_type,
                },
                "is_shared": row.is_shared,
            }
            for row in rows[:bounded_limit]
        ]
        return {"specs": specs, "count": len(specs)}

    @staticmethod
    def resolve_sigmarail_strategy_saved_spec(root, info, ir_id, tenant_id):
        tenant = _authorize_tenant(info, tenant_id)
        from .views import _accessible_strategy, _strategy_json

        reference = _accessible_strategy(tenant, info.context.user, str(ir_id).strip())
        if reference is None:
            return {"error": "Strategy spec not found.", "code": "not_found"}
        return _strategy_json(reference)

    @staticmethod
    def resolve_sigmarail_backtest_jobs(root, info, tenant_id, limit=50, status=None):
        tenant = _authorize_tenant(info, tenant_id)
        from .models import WorkspaceBacktestReference

        rows = WorkspaceBacktestReference.objects.filter(tenant=tenant).order_by("-created_at")
        if status:
            rows = rows.filter(status=str(status).strip().lower()[:24])
        bounded_limit = min(max(int(limit or 50), 1), 200)
        jobs = []
        for row in rows[:bounded_limit]:
            progress = row.progress if isinstance(row.progress, dict) else {}
            configuration = row.configuration if isinstance(row.configuration, dict) else {}
            jobs.append({
                "job_id": row.job_id,
                "run_id": row.run_id or row.job_id,
                "ir_id": row.ir_id,
                "status": row.status,
                "start_date": configuration.get("start_date"),
                "end_date": configuration.get("end_date"),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "progress": progress,
                "error_message": row.error_message,
                "result_summary": row.result_summary,
            })
        return {"jobs": jobs, "count": len(jobs)}

    @staticmethod
    def resolve_sigmarail_backtest_job(root, info, job_id, tenant_id):
        tenant = _authorize_tenant(info, tenant_id)
        from django.db.models import Q
        from .models import WorkspaceBacktestReference

        row = WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
            Q(job_id=str(job_id).strip()) | Q(run_id=str(job_id).strip())
        ).first()
        if row is None:
            return {"error": "Backtest job not found.", "code": "not_found"}
        return {
            "job_id": row.job_id,
            "run_id": row.run_id or row.job_id,
            "ir_id": row.ir_id,
            "status": row.status,
            "configuration": row.configuration if isinstance(row.configuration, dict) else {},
            "progress": row.progress if isinstance(row.progress, dict) else {},
            "error_message": row.error_message,
            "strategy_content_hash": row.strategy_content_hash,
            "result_summary": row.result_summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def resolve_sigmarail_backtest_runs(root, info, tenant_id, limit=50, ir_id=None):
        tenant = _authorize_tenant(info, tenant_id)
        from .models import WorkspaceBacktestReference
        from .views import _accessible_strategy

        rows = WorkspaceBacktestReference.objects.filter(tenant=tenant)
        if ir_id:
            if _accessible_strategy(tenant, info.context.user, str(ir_id).strip()) is None:
                return {"error": "Strategy spec not found.", "code": "not_found"}
            rows = rows.filter(ir_id=str(ir_id).strip())
        rows = rows.order_by("-created_at")
        bounded_limit = min(max(int(limit or 50), 1), 200)
        runs = []
        for row in rows[:bounded_limit]:
            runs.append({
                "run_id": row.run_id or row.job_id,
                "job_id": row.job_id,
                "ir_id": row.ir_id,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "configuration": row.configuration if isinstance(row.configuration, dict) else {},
                "result_summary": row.result_summary,
                "strategy_content_hash": row.strategy_content_hash,
            })
        return {"runs": runs, "count": len(runs)}

    @staticmethod
    def resolve_sigmarail_backtest_report(root, info, run_id, tenant_id):
        tenant = _authorize_tenant(info, tenant_id)
        from django.db.models import Q
        from .models import WorkspaceBacktestReference
        from sigmarail.features.backtest_report import get_backtest_report

        run_id = str(run_id).strip()
        if not run_id or not WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
            Q(run_id=run_id) | Q(job_id=run_id)
        ).exists():
            return {"error": "Backtest run not found.", "code": "not_found"}
        client = _clickhouse_client()
        try:
            return get_backtest_report(client, run_id)
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_backtest_compare(root, info, run_id_a, run_id_b, tenant_id):
        tenant = _authorize_tenant(info, tenant_id)
        from django.db.models import Q
        from .models import WorkspaceBacktestReference
        from sigmarail.features.backtest_report import get_backtest_report

        run_ids = [str(run_id_a).strip(), str(run_id_b).strip()]
        if not all(run_ids) or any(
            not WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
                Q(run_id=run_id) | Q(job_id=run_id)
            ).exists()
            for run_id in run_ids
        ):
            return {"error": "One or more backtest runs were not found.", "code": "not_found"}
        client = _clickhouse_client()
        try:
            reports = [get_backtest_report(client, run_id) for run_id in run_ids]
        finally:
            client.close()
        for index, report in enumerate(reports):
            if "error" in report:
                return {"error": f"run_{'a' if index == 0 else 'b'}: {report['error']}", "code": report.get("code")}
        metrics_a = reports[0].get("metrics", {})
        metrics_b = reports[1].get("metrics", {})
        comparable = (
            "total_return", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown",
            "win_rate", "profit_factor", "total_orders", "total_fees",
        )
        diff = {
            key: {
                "a": metrics_a.get(key),
                "b": metrics_b.get(key),
                "delta": round(metrics_b[key] - metrics_a[key], 6)
                if isinstance(metrics_a.get(key), (int, float)) and isinstance(metrics_b.get(key), (int, float))
                else None,
            }
            for key in comparable
        }
        return {
            "run_a": {"run_id": reports[0].get("run_id"), "ir_id": reports[0].get("ir_id"), "period": reports[0].get("period")},
            "run_b": {"run_id": reports[1].get("run_id"), "ir_id": reports[1].get("ir_id"), "period": reports[1].get("period")},
            "diff": diff,
        }

    @staticmethod
    def resolve_sigmarail_market_regime(root, info, as_of_date, tenant_id):
        _authorize_tenant(info, tenant_id)
        try:
            parsed = date.fromisoformat(str(as_of_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
        from sigmarail.features.platform_tools import get_market_regime

        client = _clickhouse_client()
        try:
            return get_market_regime(client, date=parsed.isoformat())
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_regime_allocation(root, info, as_of_date, tenant_id, policy_name=None, ticker="SPY"):
        _authorize_tenant(info, tenant_id)
        try:
            parsed = date.fromisoformat(str(as_of_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
        from sigmarail.features.platform_tools import explain_regime_allocation

        client = _clickhouse_client()
        try:
            return explain_regime_allocation(
                client, date=parsed.isoformat(), policy_name=policy_name, ticker=ticker or "SPY"
            )
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_regime_compare_periods(
        root, info, focus_start, focus_end, reference_start, reference_end, tenant_id
    ):
        _authorize_tenant(info, tenant_id)
        try:
            windows = [date.fromisoformat(str(value)) for value in (focus_start, focus_end, reference_start, reference_end)]
        except (TypeError, ValueError) as exc:
            raise ValidationError("All period bounds must be ISO dates (YYYY-MM-DD).") from exc
        if windows[0] > windows[1] or windows[2] > windows[3]:
            raise ValidationError("Each start date must be on or before its end date.")
        from sigmarail.features.platform_tools import compare_regime_periods

        client = _clickhouse_client()
        try:
            return compare_regime_periods(
                client,
                focus_start=windows[0].isoformat(),
                focus_end=windows[1].isoformat(),
                reference_start=windows[2].isoformat(),
                reference_end=windows[3].isoformat(),
            )
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_regime_entry_gate(root, info, as_of_date, tenant_id):
        _authorize_tenant(info, tenant_id)
        try:
            parsed = date.fromisoformat(str(as_of_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
        from sigmarail.features.gate_tools import evaluate_entry_gate

        client = _clickhouse_client()
        try:
            return evaluate_entry_gate(client, as_of_date=parsed.isoformat())
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_regime_transition_weight(root, info, as_of_date, tenant_id, base_weight=1.0):
        _authorize_tenant(info, tenant_id)
        try:
            parsed = date.fromisoformat(str(as_of_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
        from sigmarail.features.narrative_tools import regime_transition_weight

        client = _clickhouse_client()
        try:
            return regime_transition_weight(client, as_of_date=parsed.isoformat(), base_weight=float(base_weight or 1.0))
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_regime_rank_candidates(root, info, as_of_date, passing_tickers, tenant_id):
        _authorize_tenant(info, tenant_id)
        try:
            parsed = date.fromisoformat(str(as_of_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
        if not isinstance(passing_tickers, list) or len(passing_tickers) > 500:
            raise ValidationError("passingTickers must contain at most 500 ticker symbols.")
        from sigmarail.features.narrative_tools import rank_candidates_for_selection

        client = _clickhouse_client()
        try:
            return rank_candidates_for_selection(
                client, passing_tickers=passing_tickers, as_of_date=parsed.isoformat()
            )
        finally:
            client.close()

    @staticmethod
    def resolve_sigmarail_stock_snapshot(root, info, ticker, tenant_id, as_of_date=None):
        _authorize_tenant(info, tenant_id)

        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker or len(normalized_ticker) > 24:
            raise ValidationError("ticker must contain 1 to 24 characters.")
        if any(not (char.isalnum() or char in ".-_") for char in normalized_ticker):
            raise ValidationError("ticker contains unsupported characters.")

        where_date = "AND date <= {as_of:Date}" if as_of_date else ""
        params = {"ticker": normalized_ticker}
        parsed_as_of = None
        if as_of_date:
            try:
                parsed_as_of = date.fromisoformat(str(as_of_date))
            except ValueError as exc:
                raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
            params["as_of"] = parsed_as_of.isoformat()
        client = _clickhouse_client()
        try:
            result = client.query(
                f"""
                WITH latest AS (
                    SELECT max(date) AS latest_available_date
                    FROM screener_price_tech_daily
                    WHERE ticker = {{ticker:String}}
                ), candidate AS (
                    SELECT ticker, date, company_name, sector, industry, close, rs_rating,
                           atr_14_pct, stage_code, sma50d, sma200d
                    FROM screener_price_tech_daily
                    WHERE ticker = {{ticker:String}} {where_date}
                    ORDER BY date DESC, lastupdated DESC
                    LIMIT 1
                )
                SELECT candidate.ticker, candidate.date, candidate.company_name, candidate.sector,
                       candidate.industry, candidate.close, candidate.rs_rating, candidate.atr_14_pct,
                       candidate.stage_code, candidate.sma50d, candidate.sma200d,
                       latest.latest_available_date
                FROM latest LEFT JOIN candidate ON 1
                SETTINGS join_use_nulls = 1
                """,
                parameters=params,
            )
        finally:
            client.close()
        if not result.result_rows:
            return SigmaRailStockSnapshot(
                ticker=normalized_ticker,
                requested_as_of_date=parsed_as_of.isoformat() if parsed_as_of else None,
                availability_status="no_data_on_or_before_as_of" if parsed_as_of else "no_data",
            )
        row = dict(zip(result.column_names, result.result_rows[0]))
        actual_date = row.get("date")
        latest_date = row.get("latest_available_date")
        if actual_date is None:
            availability_status = "no_data_on_or_before_as_of" if parsed_as_of else "no_data"
        elif parsed_as_of is None:
            availability_status = "latest_available"
        elif actual_date == parsed_as_of:
            availability_status = "exact"
        else:
            availability_status = "prior_available"
        return SigmaRailStockSnapshot(
            ticker=normalized_ticker,
            as_of_date=actual_date.isoformat() if actual_date else None,
            requested_as_of_date=parsed_as_of.isoformat() if parsed_as_of else None,
            availability_status=availability_status,
            latest_available_date=latest_date.isoformat() if latest_date else None,
            company_name=row.get("company_name"), sector=row.get("sector"),
            industry=row.get("industry"), close=row.get("close"),
            rs_rating=row.get("rs_rating"), atr_14_pct=row.get("atr_14_pct"),
            stage_code=row.get("stage_code"), sma50d=row.get("sma50d"), sma200d=row.get("sma200d"),
        )


def _workspace_api_call(info, tenant, method, path, payload):
    """Call an existing tenant-authorized AppTension write API in-process."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from .views import DomainAPIRouteView, WorkspaceSavedScreensView, WorkspaceStrategySpecsView

    request = getattr(info.context, "_request", info.context)
    user = getattr(info.context, "user", None)
    views = {
        ("POST", "/api/screens/saved"): WorkspaceSavedScreensView.as_view(),
        ("POST", "/api/backtests/specs"): WorkspaceStrategySpecsView.as_view(),
        ("POST", "/api/backtests/jobs"): DomainAPIRouteView.as_view(),
    }
    view = views.get((method.upper(), path))
    if view is None:
        return {"ok": False, "code": "MUTATION_NOT_ALLOWLISTED", "message": "This mutation route is not allowlisted."}
    try:
        django_request = APIRequestFactory().post(
            path,
            data=payload,
            format="json",
            HTTP_X_TENANT_ID=to_global_id("TenantType", tenant.pk),
        )
        force_authenticate(django_request, user=user)
        if hasattr(request, "session"):
            django_request.session = request.session
        response = view(django_request)
    except Exception:
        logger.exception("SigmaRail MCP mutation could not reach %s", path)
        return {
            "ok": False,
            "code": "API_HANDLER_UNAVAILABLE",
            "message": "The AppTension mutation handler could not process this request.",
        }
    body = getattr(response, "data", None)
    if body is None:
        try:
            body = json.loads(response.content) if response.content else {}
        except (TypeError, ValueError):
            return {"ok": False, "code": "INVALID_API_RESPONSE", "status": response.status_code}
    if not isinstance(body, dict):
        return {"ok": False, "code": "INVALID_API_RESPONSE", "status": response.status_code}
    if response.status_code >= 400:
        return {
            "ok": False,
            "code": body.get("code") or f"HTTP_{response.status_code}",
            "message": body.get("detail") or "The requested mutation was rejected.",
            "status": response.status_code,
            "details": body,
        }
    return {"ok": True, "status": response.status_code, "result": body}


class Mutation(graphene.ObjectType):
    sigmarail_save_screen = GenericScalar(
        screen_name=graphene.String(required=True),
        spec=GenericScalar(required=True),
        screen_description=graphene.String(),
        source_template_id=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description=(
            "Create a private screen in the active tenant from a canonical UniverseQueryV1 AST. "
            "Compile and preview the AST first; this writes the screen to AppTension PostgreSQL."
        ),
    )
    sigmarail_save_strategy = GenericScalar(
        ir_id=graphene.String(required=True),
        title=graphene.String(required=True),
        pipeline_document=GenericScalar(required=True),
        notes=graphene.String(),
        category=graphene.String(),
        tags=graphene.List(graphene.String),
        expected_hash=graphene.String(),
        tenant_id=graphene.ID(required=True),
        description=(
            "Save a private versioned strategy in the active tenant. Validate and compile the canonical "
            "PipelineDocument before saving. Writes AppTension PostgreSQL; never launches a backtest or trades. "
            "Use expectedHash when updating an existing strategy to prevent overwriting newer edits."
        ),
    )
    sigmarail_submit_backtest = GenericScalar(
        ir_id=graphene.String(required=True),
        start_date=graphene.String(required=True),
        end_date=graphene.String(required=True),
        idempotency_key=graphene.String(required=True),
        cost_assumptions=GenericScalar(),
        out_of_sample_period=GenericScalar(),
        tenant_id=graphene.ID(required=True),
        description=(
            "Submit an asynchronous historical backtest for a saved, tenant-owned strategy. "
            "Requires a stable idempotencyKey and explicit date bounds. costAssumptions and "
            "outOfSamplePeriod are recorded as experiment metadata only; they do not change the "
            "LEAN fee/slippage model or create a second run. Inspect the resulting run before conclusions."
        ),
    )
    sigmarail_record_experiment_decision = GenericScalar(
        job_id=graphene.String(required=True),
        decision=graphene.String(required=True),
        rationale=graphene.String(required=True),
        evidence=GenericScalar(),
        tenant_id=graphene.ID(required=True),
        description=(
            "Record a tenant-owned research verdict for a successfully completed backtest. "
            "Allowed decisions are retain, revise, discard, and defer. This records a review "
            "decision only; it does not change strategies, launch jobs, or place trades."
        ),
    )

    @staticmethod
    def resolve_sigmarail_save_screen(
        root, info, tenant_id, screen_name, spec, screen_description="", source_template_id=""
    ):
        tenant = _authorize_tenant(info, tenant_id)
        screen_spec = _json_object(spec, "spec")
        try:
            from sigmarail.universe import compile_universe_spec

            compile_universe_spec(screen_spec)
        except Exception as exc:
            return {"ok": False, "code": "INVALID_SCREEN_AST", "message": str(exc)}
        result = _workspace_api_call(
            info,
            tenant,
            "POST",
            "/api/screens/saved",
            {
                "name": str(screen_name).strip(),
                "description": str(screen_description or "").strip(),
                "spec": screen_spec,
                "source_template_id": str(source_template_id or "").strip(),
            },
        )
        return result

    @staticmethod
    def resolve_sigmarail_save_strategy(
        root, info, tenant_id, ir_id, title, pipeline_document,
        notes="", category="", tags=None, expected_hash="",
    ):
        tenant = _authorize_tenant(info, tenant_id)
        pipeline_data = _json_object(pipeline_document, "pipelineDocument")
        try:
            from sigmarail_spec.strategy import PipelineDocument, compile_pipeline
            from screens.risk_rules import materialize_swing_risk_rules

            strategy_spec = compile_pipeline(PipelineDocument.model_validate(pipeline_data))
            materialize_swing_risk_rules(strategy_spec)
        except Exception as exc:
            return {"ok": False, "code": "INVALID_STRATEGY_AST", "message": str(exc)}
        payload = {
            "ir_id": str(ir_id).strip(),
            "title": str(title).strip(),
            "spec": strategy_spec,
            "pipeline_document": pipeline_data,
            "notes": str(notes or ""),
            "category": str(category or ""),
            "tags": tags or [],
            "expected_hash": str(expected_hash or ""),
        }
        return _workspace_api_call(info, tenant, "POST", "/api/backtests/specs", payload)

    @staticmethod
    def resolve_sigmarail_submit_backtest(
        root, info, tenant_id, ir_id, start_date, end_date, idempotency_key,
        cost_assumptions=None, out_of_sample_period=None,
    ):
        tenant = _authorize_tenant(info, tenant_id)
        try:
            start = date.fromisoformat(str(start_date))
            end = date.fromisoformat(str(end_date))
        except (TypeError, ValueError) as exc:
            raise ValidationError("startDate and endDate must use YYYY-MM-DD.") from exc
        if end <= start:
            raise ValidationError("endDate must be after startDate.")
        key = str(idempotency_key or "").strip()
        if len(key) < 8 or len(key) > 200:
            raise ValidationError("idempotencyKey must contain 8 to 200 characters.")
        if cost_assumptions is not None and not isinstance(cost_assumptions, dict):
            raise ValidationError("costAssumptions must be a JSON object.")
        if out_of_sample_period is not None and not isinstance(out_of_sample_period, dict):
            raise ValidationError("outOfSamplePeriod must be a JSON object.")

        from .models import WorkspaceBacktestReference
        from .views import _accessible_strategy
        from django.db.models import Q
        import hashlib
        import uuid

        strategy_id = str(ir_id or "").strip()
        strategy = _accessible_strategy(tenant, info.context.user, strategy_id)
        if strategy is None:
            return {"ok": False, "code": "STRATEGY_NOT_FOUND", "message": "Saved strategy not found in this tenant."}
        request_data = {
            "ir_id": strategy_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "strategy_content_hash": strategy.content_hash,
            "cost_assumptions": cost_assumptions or {},
            "out_of_sample_period": out_of_sample_period or {},
        }
        request_hash = hashlib.sha256(
            json.dumps(request_data, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sigmarail:{tenant.pk}:{key}"))
        existing = WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
            Q(job_id=job_id) | Q(run_id=job_id)
        ).first()
        if existing is not None:
            config = existing.configuration if isinstance(existing.configuration, dict) else {}
            if config.get("request_hash") != request_hash:
                return {
                    "ok": False,
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "This idempotencyKey was already used for a different backtest request.",
                    "job_id": existing.job_id,
                }
            return {
                "ok": True,
                "replayed": True,
                "result": {
                    "job_id": existing.job_id,
                    "run_id": existing.run_id or existing.job_id,
                    "ir_id": existing.ir_id,
                    "status": existing.status,
                    "strategy_content_hash": existing.strategy_content_hash,
                    "request_hash": request_hash,
                    "configuration": config,
                },
            }
        result = _workspace_api_call(
            info,
            tenant,
            "POST",
            "/api/backtests/jobs",
            {
                "ir_id": strategy_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "job_id": job_id,
                "idempotency_key": key,
                "request_hash": request_hash,
                "cost_assumptions": cost_assumptions or {},
                "out_of_sample_period": out_of_sample_period or {},
            },
        )
        if result.get("ok"):
            result["idempotency_key"] = key
            result["request_hash"] = request_hash
            result["strategy_content_hash"] = strategy.content_hash
        elif result.get("status") == 409:
            # A concurrent identical request may win the unique job_id insert.
            # Resolve that race to the same idempotent response contract.
            raced = WorkspaceBacktestReference.objects.filter(tenant=tenant, job_id=job_id).first()
            config = raced.configuration if raced and isinstance(raced.configuration, dict) else {}
            if raced and config.get("request_hash") == request_hash:
                return {
                    "ok": True,
                    "replayed": True,
                    "result": {
                        "job_id": raced.job_id,
                        "run_id": raced.run_id or raced.job_id,
                        "ir_id": raced.ir_id,
                        "status": raced.status,
                        "strategy_content_hash": raced.strategy_content_hash,
                        "request_hash": request_hash,
                        "configuration": config,
                    },
                }
        return result

    @staticmethod
    def resolve_sigmarail_record_experiment_decision(
        root, info, tenant_id, job_id, decision, rationale, evidence=None,
    ):
        tenant = _authorize_tenant(info, tenant_id)
        allowed = {"retain", "revise", "discard", "defer"}
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in allowed:
            raise ValidationError(f"decision must be one of: {', '.join(sorted(allowed))}.")
        rationale = str(rationale or "").strip()
        if not rationale or len(rationale) > 5000:
            raise ValidationError("rationale must contain 1 to 5000 characters.")
        if evidence is not None and not isinstance(evidence, dict):
            raise ValidationError("evidence must be a JSON object.")
        evidence = evidence or {}
        if len(json.dumps(evidence, separators=(",", ":"), default=str)) > 64000:
            raise ValidationError("evidence must be 64 KB or smaller.")

        from django.db import transaction
        from django.db.models import Q
        from .models import WorkspaceBacktestReference

        with transaction.atomic():
            reference = WorkspaceBacktestReference.objects.select_for_update().filter(tenant=tenant).filter(
                Q(job_id=str(job_id).strip()) | Q(run_id=str(job_id).strip())
            ).first()
            if reference is None:
                return {"ok": False, "code": "BACKTEST_NOT_FOUND", "message": "Backtest job not found in this tenant."}
            if reference.status != "done":
                return {
                    "ok": False,
                    "code": "BACKTEST_NOT_COMPLETE",
                    "message": "A decision can be recorded after the backtest status is done.",
                    "status": reference.status,
                }
            configuration = reference.configuration if isinstance(reference.configuration, dict) else {}
            history = configuration.get("decision_history")
            if not isinstance(history, list):
                history = []
            event = {
                "decision": normalized_decision,
                "rationale": rationale,
                "evidence": evidence,
                "recorded_at": timezone.now().isoformat(),
                "recorded_by": str(getattr(info.context.user, "pk", "")) or None,
                "strategy_content_hash": reference.strategy_content_hash,
                "request_hash": configuration.get("request_hash"),
            }
            history.append(event)
            configuration["decision_history"] = history[-50:]
            configuration["research_decision"] = event
            reference.configuration = configuration
            reference.save(update_fields=["configuration", "updated_at"])
        return {"ok": True, "job_id": reference.job_id, "decision": event}
