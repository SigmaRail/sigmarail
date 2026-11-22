"""Tenant-authorized GraphQL reads for the SigmaRail MCP tools."""

from __future__ import annotations

from datetime import date
import json
from importlib.resources import files

import graphene
from graphene.types.generic import GenericScalar
from graphql_relay import from_global_id
from rest_framework.exceptions import ValidationError

from apps.multitenancy.middleware import get_current_tenant_with_membership_check
from .core_data import _clickhouse_client, _preview_json_value


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
