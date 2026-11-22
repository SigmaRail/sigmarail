"""Tenant-authorized GraphQL reads for the SigmaRail MCP tools."""

from __future__ import annotations

from datetime import date

import graphene
from graphene.types.generic import GenericScalar
from graphql_relay import from_global_id
from rest_framework.exceptions import ValidationError

from apps.multitenancy.middleware import get_current_tenant_with_membership_check
from .core_data import _clickhouse_client


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
    as_of_date = graphene.String(required=True)
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

    sigmarail_stock_snapshot = graphene.Field(
        SigmaRailStockSnapshot,
        ticker=graphene.String(required=True),
        tenant_id=graphene.ID(required=True),
        as_of_date=graphene.String(),
        description=(
            "Read the latest or point-in-time price, trend, and relative-strength snapshot "
            "for one stock from SigmaRail's read-only daily dataset."
        ),
    )

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
            return {"error": str(exc), "code": "invalid_query"}

        client = _clickhouse_client()
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
    def resolve_sigmarail_stock_snapshot(root, info, ticker, tenant_id, as_of_date=None):
        _authorize_tenant(info, tenant_id)

        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker or len(normalized_ticker) > 24:
            raise ValidationError("ticker must contain 1 to 24 characters.")
        if any(not (char.isalnum() or char in ".-_") for char in normalized_ticker):
            raise ValidationError("ticker contains unsupported characters.")

        where_date = "AND date <= {as_of:Date}" if as_of_date else ""
        params = {"ticker": normalized_ticker}
        if as_of_date:
            try:
                parsed_as_of = date.fromisoformat(str(as_of_date))
            except ValueError as exc:
                raise ValidationError("asOfDate must be an ISO date (YYYY-MM-DD).") from exc
            params["as_of"] = parsed_as_of.isoformat()
        result = _clickhouse_client().query(
            f"""
            SELECT ticker, date, company_name, sector, industry, close, rs_rating,
                   atr_14_pct, stage_code, sma50d, sma200d
            FROM screener_price_tech_daily
            WHERE ticker = {{ticker:String}} {where_date}
            ORDER BY date DESC, lastupdated DESC
            LIMIT 1
            """,
            parameters=params,
        )
        if not result.result_rows:
            return None
        row = dict(zip(result.column_names, result.result_rows[0]))
        return SigmaRailStockSnapshot(
            ticker=row["ticker"], as_of_date=row["date"].isoformat(), company_name=row["company_name"],
            sector=row["sector"], industry=row["industry"], close=row["close"],
            rs_rating=row["rs_rating"], atr_14_pct=row["atr_14_pct"], stage_code=row["stage_code"],
            sma50d=row["sma50d"], sma200d=row["sma200d"],
        )
