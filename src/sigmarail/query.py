"""Schema-bound, read-only queries over the built-in SigmaRail core module."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sigmarail_spec.data_query import (
    DataQueryV1,
    QueryAliasExpression,
    QueryArithmeticExpression,
    QueryComputedField,
    QueryFieldExpression,
    QueryLiteralExpression,
    QueryPredicate,
)

_SPEC_DIR = Path(__file__).resolve().parent / "spec"
_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_MAX_QUERY_LIMIT = 1000


def _read_json(name: str) -> dict[str, Any]:
    return json.loads((_SPEC_DIR / name).read_text(encoding="utf-8"))


def _core_tables() -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in _read_json("lineage-manifest.json")["tables"]}


def _module_manifest() -> dict[str, Any]:
    return _read_json("module-manifest.json")


def _datasets() -> dict[str, dict[str, Any]]:
    return {row["dataset_id"]: row for row in _module_manifest()["datasets"]}


def list_datasets() -> dict[str, Any]:
    """Return compact table inventory and owning module IDs for MCP catalog use."""
    tables = _core_tables()
    datasets = _datasets()
    rows = []
    for dataset_id, item in sorted(datasets.items()):
        table = tables[item["table"]]
        rows.append(
            {
                "module_id": "sigmarail.core",
                "dataset_id": dataset_id,
                "table": item["table"],
                "kind": table["kind"],
                "frequency": item["frequency"],
                "entity_grain": item["entity_grain"],
                "column_count": len(table["columns"]),
                "lineage_roots": table["sharadar_roots"],
            }
        )
    return {"module_id": "sigmarail.core", "count": len(rows), "datasets": rows}


def describe_dataset(dataset_id: str) -> dict[str, Any]:
    """Describe one core dataset and its SQL-generated columns/lineage."""
    item = _datasets().get(str(dataset_id).strip())
    if item is None:
        raise ValueError(f"unknown core dataset: {dataset_id!r}")
    table = _core_tables().get(item["table"])
    if table is None:
        raise RuntimeError(f"core module references missing SQL table {item['table']!r}")
    fields = [
        {
            "field_id": column["id"],
            "name": column["name"],
            "type": column["type"],
            "description": column.get("comment", ""),
            "classification": column["classification"],
            "lineage_roots": column["lineage_roots"],
        }
        for column in table["columns"]
    ]
    return {
        "module_id": "sigmarail.core",
        "dataset_id": dataset_id,
        "table": table["name"],
        "frequency": item["frequency"],
        "entity_grain": item["entity_grain"],
        "time_key": item["time_key"],
        "as_of_semantics": item["as_of_semantics"],
        "direct_inputs": table["direct_inputs"],
        "lineage_roots": table["sharadar_roots"],
        "fields": fields,
    }


def _column_index() -> dict[str, tuple[str, str, dict[str, Any]]]:
    out: dict[str, tuple[str, str, dict[str, Any]]] = {}
    tables = _core_tables()
    datasets = _datasets()
    for dataset_id, dataset in datasets.items():
        table = tables[dataset["table"]]
        for column in table["columns"]:
            out[column["id"]] = (dataset_id, column["name"], column)
            # The physical name is accepted as a convenience only when unique
            # in the selected query datasets; resolution checks the join scope.
            out.setdefault(column["name"], (dataset_id, column["name"], column))
    return out


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid schema identifier {value!r}")
    return f"`{value}`"


def _is_numeric_type(value: str) -> bool:
    schema_type = value.strip()
    while schema_type.startswith(("Nullable(", "LowCardinality(")) and schema_type.endswith(")"):
        schema_type = schema_type[schema_type.index("(") + 1 : -1].strip()
    return bool(re.match(r"^(U?Int|Float|Decimal)", schema_type, re.IGNORECASE))


def _field_ref(
    reference: str,
    scope: set[str],
    columns: dict[str, tuple[str, str, dict[str, Any]]],
) -> tuple[str, str, dict[str, Any]]:
    item = columns.get(reference)
    if item is None or item[0] not in scope:
        raise ValueError(f"field {reference!r} is not available in the selected dataset scope")
    return item


def _compile_where(
    item: QueryPredicate,
    scope: set[str],
    aliases: dict[str, str],
    columns: dict[str, tuple[str, str, dict[str, Any]]],
    params: dict[str, Any],
    *,
    allowed_aliases: set[str] | None = None,
    field_outputs: dict[str, str] | None = None,
) -> str:
    if item.op == "all":
        return "(" + " AND ".join(_compile_where(x, scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs) for x in item.items) + ")"
    if item.op == "any":
        return "(" + " OR ".join(_compile_where(x, scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs) for x in item.items) + ")"
    if item.op == "not":
        return f"NOT ({_compile_where(item.item, scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs)})"
    if item.left is not None:
        left = _compile_expression(item.left, scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs)
        if item.op in {"is_null", "is_not_null"}:
            return f"isNull({left})" if item.op == "is_null" else f"isNotNull({left})"
        right = _compile_expression(item.right, scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs)
    else:
        if field_outputs is not None:
            output = field_outputs.get(item.field_id)
            if output is None:
                raise ValueError(f"post_where field {item.field_id!r} must be selected")
            left = _quote_identifier(output)
            if item.op in {"is_null", "is_not_null"}:
                return f"isNull({left})" if item.op == "is_null" else f"isNotNull({left})"
            parameter = f"p{len(params)}"
            params[parameter] = item.value
            right = f"%({parameter})s"
            operators = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            return f"({left} {operators[item.op]} {right})"
        dataset_id, physical, _ = _field_ref(item.field_id, scope, columns)
        left = f"{aliases[dataset_id]}.{_quote_identifier(physical)}"
        if item.op in {"is_null", "is_not_null"}:
            return f"isNull({left})" if item.op == "is_null" else f"isNotNull({left})"
        parameter = f"p{len(params)}"
        params[parameter] = item.value
        right = f"%({parameter})s"
    if item.op in {"is_null", "is_not_null"}:
        return f"isNull({left})" if item.op == "is_null" else f"isNotNull({left})"
    operators = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f"({left} {operators[item.op]} {right})"


def _compile_expression(
    expression: Any,
    scope: set[str],
    aliases: dict[str, str],
    columns: dict[str, tuple[str, str, dict[str, Any]]],
    params: dict[str, Any],
    *,
    allowed_aliases: set[str] | None = None,
    field_outputs: dict[str, str] | None = None,
) -> str:
    if isinstance(expression, QueryFieldExpression):
        if expression.offset:
            raise ValueError("non-zero field offsets are not yet supported by SigmaRail core queries")
        if field_outputs is not None:
            output = field_outputs.get(expression.field_id)
            if output is None:
                raise ValueError(f"post_where field {expression.field_id!r} must be selected")
            return _quote_identifier(output)
        dataset_id, physical, _ = _field_ref(expression.field_id, scope, columns)
        return f"{aliases[dataset_id]}.{_quote_identifier(physical)}"
    if isinstance(expression, QueryLiteralExpression):
        key = f"p{len(params)}"
        params[key] = expression.value
        return f"%({key})s"
    if isinstance(expression, QueryAliasExpression):
        if allowed_aliases is None or expression.alias not in allowed_aliases:
            raise ValueError(f"computed alias {expression.alias!r} is not available here")
        return _quote_identifier(expression.alias)
    if isinstance(expression, QueryArithmeticExpression):
        left = _compile_expression(expression.args[0], scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs)
        right = _compile_expression(expression.args[1], scope, aliases, columns, params, allowed_aliases=allowed_aliases, field_outputs=field_outputs)
        return f"({left} {expression.op} {right})"
    raise TypeError(f"unsupported query expression {type(expression).__name__}")


def compile_query(
    request: DataQueryV1 | dict[str, Any],
    *,
    total_limit: int | None = None,
    limit_per_date: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate IDs against the generated core module catalog and compile bounded SELECT SQL."""
    query = request if isinstance(request, DataQueryV1) else DataQueryV1.model_validate(request)
    if query.module_id != "sigmarail.core":
        raise ValueError("the core query executor accepts module_id='sigmarail.core' only")
    datasets = _datasets()
    if query.dataset_id not in datasets:
        raise ValueError(f"unknown core dataset {query.dataset_id!r}")

    relations = {row["id"]: row for row in _module_manifest()["joins"]}
    selected_datasets = [query.dataset_id]
    for join in query.joins:
        relation = relations.get(join.relationship_id)
        if relation is None or relation["from_dataset"] not in selected_datasets:
            raise ValueError(f"join {join.relationship_id!r} is not declared from the selected dataset scope")
        if relation["to_dataset"] in selected_datasets:
            raise ValueError(f"join {join.relationship_id!r} repeats a dataset")
        selected_datasets.append(relation["to_dataset"])

    aliases = {dataset_id: f"d{index}" for index, dataset_id in enumerate(selected_datasets)}
    allowed = set(selected_datasets)
    columns = _column_index()
    params: dict[str, Any] = {}
    projections: list[str] = []
    result_names: set[str] = set()
    selected_outputs: dict[str, str] = {}
    for field in query.select:
        dataset_id, physical, _ = _field_ref(field.field_id, allowed, columns)
        output = field.alias or physical
        if output in result_names:
            raise ValueError(f"duplicate result field {output!r}; provide a unique alias")
        result_names.add(output)
        selected_outputs[field.field_id] = output
        selected_outputs.setdefault(physical, output)
        projections.append(f"{aliases[dataset_id]}.{_quote_identifier(physical)} AS {_quote_identifier(output)}")

    available_aliases: set[str] = set(result_names)
    for computed in query.computed:
        if computed.alias in result_names:
            raise ValueError(f"duplicate result field {computed.alias!r}")
        if computed.where is not None:
            expression_sql = _compile_where(
                computed.where, allowed, aliases, columns, params, allowed_aliases=available_aliases
            )
            expression_sql = f"toUInt8(ifNull(({expression_sql}), 0))"
        elif computed.expr is not None:
            expression_sql = _compile_expression(
                computed.expr, allowed, aliases, columns, params, allowed_aliases=available_aliases
            )
        elif computed.sum_aliases is not None:
            expression_sql = "(" + " + ".join(_quote_identifier(name) for name in computed.sum_aliases) + ")"
        elif computed.mean_available is not None:
            fields = []
            for field_id in computed.mean_available:
                _, _, column = _field_ref(field_id, allowed, columns)
                if not _is_numeric_type(str(column.get("type", ""))):
                    raise ValueError(f"mean_available field {field_id!r} must have a numeric schema type")
                fields.append(
                    _compile_expression(QueryFieldExpression(field_id=field_id), allowed, aliases, columns, params)
                )
            numerator = " + ".join(f"toFloat64(ifNull({field}, 0))" for field in fields)
            denominator = " + ".join(f"toUInt32(isNotNull({field}))" for field in fields)
            expression_sql = f"if(({denominator}) = 0, NULL, ({numerator}) / ({denominator}))"
        else:
            raise ValueError(f"computed field {computed.alias!r} has no expression")
        projections.append(f"{expression_sql} AS {_quote_identifier(computed.alias)}")
        result_names.add(computed.alias)
        available_aliases.add(computed.alias)

    first = datasets[query.dataset_id]
    # ClickHouse expects the alias before the FINAL modifier (``table AS d0 FINAL``).
    from_sql = f"{_quote_identifier(first['table'])} AS {aliases[query.dataset_id]} FINAL"
    for join in query.joins:
        relation = relations[join.relationship_id]
        target_id = relation["to_dataset"]
        target = datasets[target_id]
        join_terms = []
        for key in relation["keys"]:
            left_id = relation["from_dataset"]
            join_terms.append(
                f"{aliases[left_id]}.{_quote_identifier(key['from'])} = "
                f"{aliases[target_id]}.{_quote_identifier(key['to'])}"
            )
        join_type = relation.get("join_type", "left_any").upper().replace("_", " ")
        if join_type not in {"LEFT ANY", "INNER"}:
            raise ValueError(f"unsupported declared core join type {join_type!r}")
        from_sql += (
            f" {join_type} JOIN {_quote_identifier(target['table'])} AS {aliases[target_id]} FINAL"
            f" ON {' AND '.join(join_terms)}"
        )

    predicates: list[str] = []
    if query.as_of_date or query.start_date:
        time_key = first.get("time_key")
        if not time_key or first.get("as_of_semantics") == "unspecified":
            raise ValueError("this dataset has no reviewed as-of semantics; filter its time field explicitly")
        time_column = f"{aliases[query.dataset_id]}.{_quote_identifier(time_key)}"
        if query.as_of_date:
            params["as_of_date"] = query.as_of_date.isoformat()
            predicates.append(f"{time_column} = toDate(%(as_of_date)s)")
        else:
            params["start_date"] = query.start_date.isoformat()
            params["end_date"] = query.end_date.isoformat()
            predicates.append(f"{time_column} BETWEEN toDate(%(start_date)s) AND toDate(%(end_date)s)")
    if query.where is not None:
        predicates.append(_compile_where(query.where, allowed, aliases, columns, params))
    if not predicates:
        raise ValueError("a core query needs an as-of/date range or a filter to bound the read")

    sql = f"SELECT {', '.join(projections)} FROM {from_sql} WHERE {' AND '.join(predicates)}"
    if query.post_where is not None:
        post = _compile_where(
            query.post_where,
            allowed,
            aliases,
            columns,
            params,
            allowed_aliases=available_aliases,
            field_outputs=selected_outputs,
        )
        sql = f"SELECT * FROM ({sql}) AS q WHERE {post}"
    order: list[str] = []
    for item in query.order_by:
        if item.expr is not None:
            expression_sql = _compile_expression(
                item.expr,
                allowed,
                aliases,
                columns,
                params,
                allowed_aliases=available_aliases,
                field_outputs=selected_outputs if query.post_where is not None else None,
            )
        else:
            dataset_id, physical, _ = _field_ref(item.field_id, allowed, columns)
            if query.post_where is not None:
                output = selected_outputs.get(item.field_id) or selected_outputs.get(physical)
                if output is None:
                    raise ValueError("post_where queries may order by selected fields or computed aliases only")
                expression_sql = _quote_identifier(output)
            else:
                expression_sql = f"{aliases[dataset_id]}.{_quote_identifier(physical)}"
        order.append(f"{expression_sql} {item.direction.upper()}")
    if order:
        sql += " ORDER BY " + ", ".join(order)
    limit = min(total_limit if total_limit is not None else query.limit, 500_000 if total_limit is not None else _MAX_QUERY_LIMIT)
    if limit_per_date is not None:
        if not 1 <= limit_per_date <= 5000:
            raise ValueError("limit_per_date must be between 1 and 5000")
        sql += f" LIMIT {limit_per_date} BY {_quote_identifier('date')} LIMIT {limit}"
    else:
        sql += f" LIMIT {limit}"
    return sql, params


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def query_dataset(
    request: DataQueryV1 | dict[str, Any],
    client: Any | None = None,
    *,
    total_limit: int | None = None,
    limit_per_date: int | None = None,
) -> dict[str, Any]:
    """Execute a parameterized SELECT through ClickHouse's query-only client method."""
    try:
        query = request if isinstance(request, DataQueryV1) else DataQueryV1.model_validate(request)
    except ValidationError as exc:
        return {"error": str(exc), "code": "invalid_query"}
    try:
        sql, params = compile_query(query, total_limit=total_limit, limit_per_date=limit_per_date)
        if client is None:
            from sigmarail.database import get_client

            client = get_client()
        result = client.query(sql, parameters=params)
        rows = [
            {name: _json_value(value) for name, value in zip(result.column_names, row)}
            for row in result.result_rows
        ]
        query_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        return {
            "module_id": "sigmarail.core",
            "dataset_id": query.dataset_id,
            "query_hash": query_hash,
            "columns": list(result.column_names),
            "row_count": len(rows),
            "rows": rows,
            "limit": query.limit,
        }
    except Exception as exc:  # returned as MCP/API envelope; no mutation method is called
        return {"error": str(exc), "code": "query_failed"}
