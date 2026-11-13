"""LEAN-compatible universe API adapter over SigmaRail's declared core datasets.

This module accepts the existing ``universe_query_v1`` request shape, resolves its
field names against the core schema catalog, and lowers it to the versioned
``DataQueryV1`` contract. It never accepts SQL fragments or caller-defined joins.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from pydantic import ValidationError

from sigmarail_spec.data_query import (
    DataQueryV1,
    QueryAliasExpression,
    QueryArithmeticExpression,
    QueryComputedField,
    QueryField,
    QueryFieldExpression,
    QueryJoin,
    QueryLiteralExpression,
    QueryOrder,
    QueryPredicate,
)

from sigmarail.query import _column_index, _core_tables, _datasets, _module_manifest, _quote_identifier, compile_query, query_dataset

CORE_UNIVERSE = "sigmarail.core.screener_price_tech_daily"
UNIVERSE_TABLES = {
    "screener_price_tech_daily",
    "screener_fundamentals_daily",
    "screener_ratings_daily",
    "screener_stage_weekly_daily",
    "screener_ownership_daily",
}
LEGACY_PREFIX_TABLE = {
    "px": "screener_price_tech_daily",
    "fd": "screener_fundamentals_daily",
    "rt": "screener_ratings_daily",
    "st": "screener_stage_weekly_daily",
    "ow": "screener_ownership_daily",
}
_COMPARISONS = {"eq", "neq", "gt", "gte", "lt", "lte"}


class UniverseRequestError(ValueError):
    """A malformed or unsupported universe query."""


def _catalog() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    tables = _core_tables()
    datasets = _datasets()
    by_table = {
        row["table"]: (dataset_id, row)
        for dataset_id, row in datasets.items()
        if row["table"] in UNIVERSE_TABLES
    }
    return tables, datasets, by_table


def _resolve_field(name: str, *, prior_aliases: set[str] | None = None) -> tuple[str, str, dict[str, Any]]:
    """Resolve a legacy field name to its stable ID, preferring the universe spine."""
    raw = str(name).strip().strip("`")
    if prior_aliases and raw in prior_aliases:
        raise UniverseRequestError(f"{raw!r} is a computed alias, not a schema field")
    table_hint = None
    if "." in raw:
        prefix, raw = raw.split(".", 1)
        table_hint = LEGACY_PREFIX_TABLE.get(prefix)
        if table_hint is None:
            raise UniverseRequestError(f"qualified field prefix {prefix!r} is not supported")
    tables, datasets, by_table = _catalog()
    candidates = []
    for table_name in sorted(UNIVERSE_TABLES):
        if table_hint is not None and table_name != table_hint:
            continue
        record = by_table.get(table_name)
        if record is None:
            continue
        dataset_id, _ = record
        for col in tables[table_name]["columns"]:
            if col["name"] == raw or col["id"] == raw:
                candidates.append((dataset_id, col["name"], col))
    if not candidates:
        raise UniverseRequestError(f"field {name!r} is not registered in SigmaRail's core universe datasets")
    spine_id = by_table["screener_price_tech_daily"][0]
    spine_matches = [item for item in candidates if item[0] == spine_id]
    if spine_matches:
        return spine_matches[0]
    if len(candidates) > 1:
        names = sorted({item[0].rsplit(".", 1)[-1] for item in candidates})
        raise UniverseRequestError(f"field {name!r} is ambiguous across core datasets: {names}")
    return candidates[0]


def _walk_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        if value.get("type") == "col" and isinstance(value.get("name"), str):
            names.add(value["name"])
        for child in value.values():
            names.update(_walk_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_walk_names(child))
    return names


def _field_ids(spec: dict[str, Any]) -> dict[str, str]:
    names: set[str] = set()
    for name in spec.get("select", []):
        names.add(str(name))
    for key in ("where", "post_where", "computed", "order_by"):
        names.update(_walk_names(spec.get(key)))
    for item in spec.get("computed", []):
        if isinstance(item, dict) and isinstance(item.get("mean_available"), list):
            names.update(str(name) for name in item["mean_available"])
    for item in spec.get("order_by", []):
        if isinstance(item, dict) and item.get("field"):
            names.add(str(item["field"]))
    # LEAN's cache is keyed by (date, ticker); return these fields even if omitted
    # from the authored select list, matching the old query service behavior.
    names.update({"ticker", "date"})
    resolved: dict[str, str] = {}
    for name in sorted(names):
        if name in {item.get("alias") for item in spec.get("computed", []) if isinstance(item, dict)}:
            continue
        dataset_id, _, column = _resolve_field(name)
        resolved[name] = column["id"]
    return resolved


def _expression(raw: Any, field_ids: dict[str, str], aliases: set[str]) -> Any:
    if not isinstance(raw, dict):
        raise UniverseRequestError("expression nodes must be JSON objects")
    kind = raw.get("type")
    if kind == "col":
        name = str(raw.get("name", ""))
        offset = int(raw.get("offset", 0))
        if name in aliases:
            if offset:
                raise UniverseRequestError("offsets on computed aliases are not supported")
            return QueryAliasExpression(alias=name)
        try:
            field_id = field_ids[name]
        except KeyError as exc:
            raise UniverseRequestError(f"column {name!r} was not resolved in the core field catalog") from exc
        return QueryFieldExpression(field_id=field_id, offset=offset)
    if kind == "lit":
        return QueryLiteralExpression(value=raw.get("value"))
    if kind == "formula":
        op = raw.get("op")
        if op not in {"+", "-", "*", "/"}:
            raise UniverseRequestError(f"arithmetic operator {op!r} is not supported")
        args = raw.get("args")
        if not isinstance(args, list) or len(args) != 2:
            raise UniverseRequestError("formula nodes require exactly two args")
        return QueryArithmeticExpression(op=op, args=[_expression(args[0], field_ids, aliases), _expression(args[1], field_ids, aliases)])
    raise UniverseRequestError(f"expression node type {kind!r} is not supported")


def _predicate(raw: Any, field_ids: dict[str, str], aliases: set[str]) -> QueryPredicate | None:
    if not isinstance(raw, dict):
        raise UniverseRequestError("predicate nodes must be JSON objects")
    op = raw.get("type")
    if op in {"all", "any"}:
        items = raw.get("items")
        if not isinstance(items, list):
            raise UniverseRequestError(f"{op} predicates require a non-empty items list")
        if not items and op == "all":
            return None
        if not items:
            raise UniverseRequestError("any predicates require a non-empty items list")
        return QueryPredicate(op=op, items=[_predicate(item, field_ids, aliases) for item in items])
    if op == "not":
        item = _predicate(raw.get("item"), field_ids, aliases)
        if item is None:
            raise UniverseRequestError("not cannot wrap an empty all predicate")
        return QueryPredicate(op="not", item=item)
    if op in _COMPARISONS:
        return QueryPredicate(
            op=op,
            left=_expression(raw.get("left"), field_ids, aliases),
            right=_expression(raw.get("right"), field_ids, aliases),
        )
    raise UniverseRequestError(f"predicate type {op!r} is not supported")


def _collect_used_datasets(field_ids: dict[str, str]) -> set[str]:
    columns = _column_index()
    return {columns[field_id][0] for field_id in field_ids.values()}


def _adapt_universe_request(body: dict[str, Any]) -> tuple[DataQueryV1, dict[str, Any]]:
    start = body.get("start_date")
    end = body.get("end_date")
    if not start or not end:
        raise UniverseRequestError("start_date and end_date are required")
    if body.get("mode", "detail") != "detail":
        raise UniverseRequestError("SigmaRail universe API supports mode='detail' only")
    if body.get("export_format", "objects") != "objects":
        raise UniverseRequestError("SigmaRail universe API supports export_format='objects' only")
    spec = body.get("spec")
    if not isinstance(spec, dict) or spec.get("version") not in (1, 2):
        raise UniverseRequestError("spec must be a universe_query_v1/v2 object")
    if spec.get("spine", "screener_price_tech_daily") != "screener_price_tech_daily":
        raise UniverseRequestError("SigmaRail core universe currently supports screener_price_tech_daily as its spine")
    if spec.get("from") not in (None, "screener", "daily_screener"):
        raise UniverseRequestError("legacy 'from' must be 'screener' or 'daily_screener'")
    if spec.get("where_sql"):
        raise UniverseRequestError("where_sql is unsupported; use the bounded JSON expression AST")
    select = spec.get("select")
    if not isinstance(select, list) or not select or any(not isinstance(x, str) for x in select):
        raise UniverseRequestError("spec.select must be a non-empty list of field names")
    per_day = spec.get("limit_per_day")
    if not isinstance(per_day, int) or isinstance(per_day, bool) or not 1 <= per_day <= 5000:
        raise UniverseRequestError("spec.limit_per_day must be between 1 and 5000")
    total_limit = body.get("limit", 500_000)
    if not isinstance(total_limit, int) or isinstance(total_limit, bool) or not 1 <= total_limit <= 500_000:
        raise UniverseRequestError("limit must be between 1 and 500000")
    if spec.get("joins"):
        raise UniverseRequestError("caller-defined joins are not supported; SigmaRail resolves declared core joins from fields")
    if not spec.get("where"):
        raise UniverseRequestError("spec.where is required and must use the bounded JSON expression AST")
    if not spec.get("order_by"):
        raise UniverseRequestError("spec.order_by must contain at least one deterministic sort item")
    if not isinstance(spec.get("computed", []), list):
        raise UniverseRequestError("spec.computed must be a list")

    field_ids = _field_ids(spec)
    query_select_names = list(select)
    selected_physical = {_resolve_field(name)[1] for name in query_select_names}
    for required in ("ticker", "date"):
        if required not in selected_physical:
            query_select_names.append(required)
    query_fields = []
    seen_field_ids: set[str] = set()
    for name in query_select_names:
        field_id = field_ids[name]
        if field_id not in seen_field_ids:
            query_fields.append(QueryField(field_id=field_id))
            seen_field_ids.add(field_id)

    computed_rows = spec.get("computed", [])
    aliases: set[str] = set()
    computed: list[QueryComputedField] = []
    for item in computed_rows:
        if not isinstance(item, dict):
            raise UniverseRequestError("computed entries must be objects")
        alias = item.get("alias")
        kind = item.get("kind")
        payloads = [key for key in ("where", "expr", "sum_aliases", "mean_available") if key in item]
        if len(payloads) != 1:
            raise UniverseRequestError("computed entries require exactly one of where, expr, sum_aliases, mean_available")
        payload_key = payloads[0]
        args: dict[str, Any] = {"alias": alias, "kind": kind}
        if payload_key == "where":
            if kind != "bool":
                raise UniverseRequestError("computed where expressions require kind='bool'")
            args["where"] = _predicate(item[payload_key], field_ids, aliases)
        elif payload_key == "expr":
            if kind != "number":
                raise UniverseRequestError("computed expr requires kind='number'")
            args["expr"] = _expression(item[payload_key], field_ids, aliases)
        elif payload_key == "sum_aliases":
            if kind != "number":
                raise UniverseRequestError("sum_aliases requires kind='number'")
            args["sum_aliases"] = item[payload_key]
        else:
            if kind != "number":
                raise UniverseRequestError("mean_available requires kind='number'")
            try:
                args["mean_available"] = [field_ids[name] for name in item[payload_key]]
            except (KeyError, TypeError) as exc:
                raise UniverseRequestError("mean_available must list registered field names") from exc
        computed.append(QueryComputedField.model_validate(args))
        aliases.add(alias)

    where_raw = spec["where"]
    where = _predicate(where_raw, field_ids, set())
    post_where = _predicate(spec["post_where"], field_ids, aliases) if spec.get("post_where") else None
    selected_or_computed = set(select) | aliases | {"ticker", "date"}
    requested_order: list[QueryOrder] = []
    for item in spec["order_by"]:
        if not isinstance(item, dict):
            raise UniverseRequestError("order_by entries must be objects")
        direction = str(item.get("direction", "desc")).lower()
        if direction not in {"asc", "desc"}:
            raise UniverseRequestError("order_by direction must be asc or desc")
        if item.get("field") is not None:
            name = str(item["field"])
            if name not in selected_or_computed:
                raise UniverseRequestError(f"order_by field {name!r} must be selected or computed")
            if name in aliases:
                requested_order.append(QueryOrder(expr=QueryAliasExpression(alias=name), direction=direction))
            else:
                requested_order.append(QueryOrder(field_id=field_ids[name], direction=direction))
        elif item.get("expr") is not None:
            requested_order.append(QueryOrder(expr=_expression(item["expr"], field_ids, aliases), direction=direction))
        else:
            raise UniverseRequestError("order_by entries require field or expr")

    # Match the old service's stable date/rank/ticker ordering so backtest chunks
    # are deterministic even when user ranks tie.
    order_by = []
    requested_fields = [str(item.get("field")) for item in spec["order_by"] if isinstance(item, dict)]
    if "date" not in requested_fields:
        order_by.append(QueryOrder(field_id=field_ids["date"], direction="asc"))
    order_by.extend(requested_order)
    if "ticker" not in requested_fields:
        order_by.append(QueryOrder(field_id=field_ids["ticker"], direction="asc"))

    used_datasets = _collect_used_datasets(field_ids)
    used_datasets.add(CORE_UNIVERSE)
    join_rows = _module_manifest()["joins"]
    joins = []
    for relation in join_rows:
        if relation["from_dataset"] == CORE_UNIVERSE and relation["to_dataset"] in used_datasets:
            joins.append(QueryJoin(relationship_id=relation["id"]))

    total_field_map = dict(field_ids)
    query = DataQueryV1(
        module_id="sigmarail.core",
        dataset_id=CORE_UNIVERSE,
        joins=joins,
        select=query_fields,
        computed=computed,
        where=where,
        post_where=post_where,
        start_date=date.fromisoformat(str(start)[:10]),
        end_date=date.fromisoformat(str(end)[:10]),
        order_by=order_by,
        limit=min(total_limit, 1000),
    )
    return query, {
        "start_date": str(start)[:10],
        "end_date": str(end)[:10],
        "mode": "detail",
        "limit": total_limit,
        "limit_per_day": per_day,
        "select": list(select),
        "computed_aliases": [item.alias for item in computed],
        "order_by": spec["order_by"],
        "required_fields": list(dict.fromkeys([*select, *[item["alias"] for item in computed_rows], "ticker", "date"])),
    }


def registry_digest() -> str:
    payload = {
        "lineage": _core_tables(),
        "modules": _module_manifest(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_universe_spec(
    spec: dict[str, Any],
    *,
    start_date: str = "1970-01-01",
    end_date: str = "1970-01-01",
    total_limit: int = 500_000,
) -> tuple[str, dict[str, Any]]:
    """Validate a universe spec and compile it with the SigmaRail query compiler."""
    request = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": total_limit,
        "spec": spec,
    }
    query, envelope = _adapt_universe_request(request)
    return compile_query(
        query,
        total_limit=envelope["limit"],
        limit_per_date=envelope["limit_per_day"],
    )


def universe_membership_counts(
    spec: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    """Aggregate schema-validated universe membership by date without row truncation."""
    body = {"start_date": start_date, "end_date": end_date, "limit": 500_000, "spec": spec}
    query, _ = _adapt_universe_request(body)
    source_sql, params = compile_query(query, include_ordering=False, include_limits=False)
    if client is None:
        from sigmarail.database import get_client

        client = get_client()
    result = client.query(
        f"""
        SELECT toString(q.`date`) AS day, count() AS member_count
        FROM ({source_sql}) AS q
        GROUP BY q.`date`
        ORDER BY q.`date`
        SETTINGS max_execution_time = 30,
          max_rows_to_read = 500000000,
          timeout_before_checking_execution_speed = 0
        """,
        parameters=params,
    )
    return [{"date": str(row[0]), "count": int(row[1])} for row in result.result_rows]


def universe_measure_series(
    spec: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    aliases: list[str],
    screens_hit: bool = False,
    funnel_aliases: list[str] | None = None,
    client: Any | None = None,
) -> dict[str, list[float]]:
    """Aggregate validated computed measures by date for Studio's stage probe."""
    computed_kinds = {
        str(item.get("alias")): str(item.get("kind", ""))
        for item in spec.get("computed", [])
        if isinstance(item, dict) and item.get("alias")
    }
    computed_names = set(computed_kinds)
    requested = list(dict.fromkeys(str(name) for name in aliases if name))
    funnel = list(dict.fromkeys(str(name) for name in (funnel_aliases or []) if name and name != "screens_hit"))
    needs_screens_hit = screens_hit and "screens_hit" in computed_names
    if any(name not in computed_names for name in [*requested, *funnel]):
        raise UniverseRequestError("measure aliases must be declared in spec.computed")
    if not requested and not needs_screens_hit and not funnel:
        return {}

    body = {"start_date": start_date, "end_date": end_date, "limit": 500_000, "spec": spec}
    query, _ = _adapt_universe_request(body)
    source_sql, params = compile_query(query, include_ordering=False, include_limits=False)
    from sigmarail.query import _quote_identifier

    projections = ["toString(q.`date`) AS day"]
    out_names: list[str] = []
    for alias in requested:
        aggregate = (
            f"sum(toUInt8(u.{_quote_identifier(alias)}))"
            if computed_kinds.get(alias) == "bool"
            else f"sum(toFloat64(u.{_quote_identifier(alias)}))"
        )
        projections.append(f"{aggregate} AS {_quote_identifier('sum_' + alias)}")
        out_names.append("sum_" + alias)
    if needs_screens_hit:
        projections.append(f"avg(toFloat64(q.{_quote_identifier('screens_hit')})) AS avg_screens_hit")
        out_names.append("screens_hit")
    if funnel:
        predicate = " AND ".join(f"u.{_quote_identifier(alias)} = 1" for alias in funnel)
        projections.append(f"sum(if(({predicate}), 1, 0)) AS sum_funnel")
        out_names.append("funnel")
    if client is None:
        from sigmarail.database import get_client
        client = get_client()
    result = client.query(
        f"""
        SELECT {', '.join(projections)}
        FROM ({source_sql}) AS u
        GROUP BY u.`date`
        ORDER BY u.`date`
        LIMIT 1000
        SETTINGS max_execution_time = 30,
          max_rows_to_read = 500000000,
          timeout_before_checking_execution_speed = 0
        """,
        parameters=params,
    )
    series: dict[str, list[float]] = {name: [] for name in out_names}
    for row in result.result_rows:
        for index, name in enumerate(out_names, start=1):
            try:
                value = float(row[index])
                series[name].append(round(value, 4) if value == value and abs(value) != float("inf") else 0.0)
            except (TypeError, ValueError, IndexError):
                series[name].append(0.0)
    # Consumers expect one pass-count series for each requested bool alias and
    # one cumulative funnel series, plus the optional screens_hit measure.
    return {
        **{alias: series.get("sum_" + alias, []) for alias in requested},
        **({"screens_hit": series.get("screens_hit", [])} if needs_screens_hit else {}),
        **({"funnel": series.get("funnel", [])} if funnel else {}),
    }


def universe_membership_by_ticker(
    spec: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    tickers: list[str] | None = None,
    client: Any | None = None,
) -> dict[str, int]:
    """Aggregate membership duration by ticker using the same validated universe query."""
    body = {"start_date": start_date, "end_date": end_date, "limit": 500_000, "spec": spec}
    query, _ = _adapt_universe_request(body)
    source_sql, params = compile_query(query, include_ordering=False, include_limits=False)
    if client is None:
        from sigmarail.database import get_client

        client = get_client()
    ticker_filter = ""
    if tickers:
        clean = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))[:5000]
        if clean:
            params["membership_tickers"] = clean
            ticker_filter = "WHERE q.`ticker` IN {membership_tickers:Array(String)}"
    result = client.query(
        f"""
        SELECT q.`ticker` AS ticker, count() AS days_in_universe
        FROM ({source_sql}) AS q
        {ticker_filter}
        GROUP BY q.`ticker`
        ORDER BY q.`ticker`
        LIMIT 10000
        SETTINGS max_execution_time = 30,
          max_rows_to_read = 500000000,
          timeout_before_checking_execution_speed = 0
        """,
        parameters=params,
    )
    return {str(row[0]).upper(): int(row[1]) for row in result.result_rows}


def universe_membership_samples(
    spec: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    sample_dates: list[str],
    client: Any | None = None,
) -> list[dict[str, str]]:
    """Return a bounded ticker sample for selected dates from the validated universe."""
    if not sample_dates:
        return []
    body = {"start_date": start_date, "end_date": end_date, "limit": 500_000, "spec": spec}
    query, _ = _adapt_universe_request(body)
    source_sql, params = compile_query(query, include_ordering=False, include_limits=False)
    if client is None:
        from sigmarail.database import get_client

        client = get_client()
    params["sample_dates"] = sample_dates
    result = client.query(
        f"""
        SELECT toString(q.`date`) AS day, q.`ticker` AS ticker
        FROM ({source_sql}) AS q
        WHERE toString(q.`date`) IN {{sample_dates:Array(String)}}
        ORDER BY q.`date`, q.`ticker`
        LIMIT 500
        SETTINGS max_execution_time = 30,
          max_rows_to_read = 500000000,
          timeout_before_checking_execution_speed = 0
        """,
        parameters=params,
    )
    return [{"date": str(row[0]), "ticker": str(row[1]).upper()} for row in result.result_rows]


def metadata() -> dict[str, Any]:
    tables, _, by_table = _catalog()
    field_count = sum(len(tables[table]["columns"]) for table in UNIVERSE_TABLES)
    return {
        "api_version": "1.0",
        "dialect": {"id": "C-VERA-EXPR-V1", "version": "1"},
        "registry_digest": registry_digest(),
        "field_count": field_count,
        "l7_sources": sorted(LEGACY_PREFIX_TABLE),
    }


def source_list() -> dict[str, Any]:
    return {
        "registry_digest": registry_digest(),
        "count": len(LEGACY_PREFIX_TABLE),
        "sources": [
            {"prefix": prefix, "table": table}
            for prefix, table in sorted(LEGACY_PREFIX_TABLE.items())
        ],
    }


def source_fields(source: str) -> dict[str, Any]:
    table = LEGACY_PREFIX_TABLE.get(source)
    if table is None:
        raise KeyError(f"unknown SigmaRail core universe source {source!r}")
    table_row = _core_tables()[table]
    fields = [
        {
            "name": column["name"],
            "sql": f"{source}.{_quote_identifier(column['name'])}",
            "alias": column["name"],
        }
        for column in table_row["columns"]
    ]
    return {
        "source": source,
        "registry_digest": registry_digest(),
        "field_count": len(fields),
        "fields": fields,
    }


def field_catalog() -> list[dict[str, Any]]:
    """Return registered fields usable by the SigmaRail universe query API."""
    tables, _, by_table = _catalog()
    rows: list[dict[str, Any]] = []
    for prefix, table_name in sorted(LEGACY_PREFIX_TABLE.items()):
        registered = by_table.get(table_name)
        if registered is None:
            continue
        dataset_id, _ = registered
        for column in tables[table_name]["columns"]:
            rows.append(
                {
                    "field_id": column["id"],
                    "name": column["name"],
                    "prefix": prefix,
                    "table": table_name,
                    "dataset_id": dataset_id,
                    "type": column["type"],
                    "description": column.get("comment", ""),
                    "classification": column.get("classification", ""),
                    "lineage_roots": column.get("lineage_roots", []),
                }
            )
    return rows


def universe_run(body: dict[str, Any], client: Any | None = None) -> dict[str, Any]:
    try:
        query, envelope = _adapt_universe_request(body)
        compile_query(query, total_limit=envelope["limit"], limit_per_date=envelope["limit_per_day"])
        result = query_dataset(
            query,
            client=client,
            total_limit=envelope["limit"],
            limit_per_date=envelope["limit_per_day"],
        )
        if "error" in result:
            return result
        return {
            **envelope,
            "registry_digest": registry_digest(),
            "row_count": result["row_count"],
            "rows": result["rows"],
        }
    except (ValidationError, TypeError, ValueError, KeyError) as exc:
        return {"error": str(exc), "code": "invalid_query"}
