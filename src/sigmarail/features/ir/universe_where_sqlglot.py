"""WHERE string → parameterized SQL using **sqlglot** (core `vera` dependency).

Only a conservative subset of expressions is allowed; identifiers must match
``universe_query_v1`` column allowlist (no subqueries, UDF calls, or ``SELECT``).
"""

from __future__ import annotations

from typing import Any, Iterator

_MAX_DEPTH = 24
_MAX_LEN = 2048


def _require_sqlglot():  # type: ignore[no-untyped-def]
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as e:  # pragma: no cover - exercised when extra missing
        raise RuntimeError(
            "where_sql requires sqlglot (listed in vera install_requires). "
            "Re-install the package: pip install -e ."
        ) from e
    return sqlglot, exp


def _next_key(params: dict[str, object], prefix: str) -> str:
    i = 0
    while True:
        k = f"{prefix}{i}"
        if k not in params:
            return k
        i += 1


def _emit_literal_py(value: Any, params: dict[str, object], prefix: str) -> str:
    k = _next_key(params, prefix)
    if isinstance(value, bool):
        params[k] = 1 if value else 0
        return f"{{{k}:UInt8}}"
    if isinstance(value, int) and not isinstance(value, bool):
        params[k] = int(value)
        return f"{{{k}:Int64}}"
    if isinstance(value, float):
        params[k] = float(value)
        return f"{{{k}:Float64}}"
    if isinstance(value, str):
        params[k] = str(value)
        return f"{{{k}:String}}"
    raise ValueError(f"unsupported literal in where_sql: {value!r}")


def _column_sql_from_parts(table: str | None, name: str) -> str:
    from sigmarail.features.ir.universe_query_v1 import universe_v1_column_sql_expression

    name = str(name).strip("`")
    if table:
        qual = f"{str(table).strip('`')}.{name}"
        try:
            return universe_v1_column_sql_expression(qual)
        except ValueError:
            pass
    return universe_v1_column_sql_expression(name)


def _flatten_bin(node: Any, op_cls: type, exp: Any) -> Iterator[Any]:
    if isinstance(node, op_cls):
        yield from _flatten_bin(node.left, op_cls, exp)
        yield from _flatten_bin(node.right, op_cls, exp)
    else:
        yield node


def _emit(node: Any, params: dict[str, object], prefix: str, depth: int, exp: Any) -> str:
    if depth > _MAX_DEPTH:
        raise ValueError("where_sql expression too deep")

    if isinstance(node, exp.Paren):
        return f"({_emit(node.this, params, prefix, depth + 1, exp)})"

    if isinstance(node, exp.Not):
        inner = node.this
        return f"NOT ({_emit(inner, params, prefix, depth + 1, exp)})"

    if isinstance(node, exp.And):
        parts = [_emit(x, params, prefix, depth + 1, exp) for x in _flatten_bin(node, exp.And, exp)]
        return " AND ".join(f"({p})" for p in parts)

    if isinstance(node, exp.Or):
        parts = [_emit(x, params, prefix, depth + 1, exp) for x in _flatten_bin(node, exp.Or, exp)]
        return " OR ".join(f"({p})" for p in parts)

    for cls, sym in (
        (exp.GT, ">"),
        (exp.GTE, ">="),
        (exp.LT, "<"),
        (exp.LTE, "<="),
        (exp.EQ, "="),
    ):
        if isinstance(node, cls):
            left = _emit(node.left, params, prefix + "L", depth + 1, exp)
            right = _emit(node.right, params, prefix + "R", depth + 1, exp)
            return f"{left} {sym} {right}"

    if isinstance(node, exp.Column):
        t = node.table
        tname = str(t) if t is not None else None
        cname = str(node.name)
        return _column_sql_from_parts(tname, cname)

    if isinstance(node, exp.Identifier):
        return _column_sql_from_parts(None, str(node.this))

    if isinstance(node, exp.Literal):
        raw = node.this
        if node.is_string:
            return _emit_literal_py(str(raw), params, prefix + "lit_")
        s = str(raw)
        if "." in s or "e" in s.lower() or "E" in s:
            return _emit_literal_py(float(s), params, prefix + "lit_")
        return _emit_literal_py(int(s), params, prefix + "lit_")

    if isinstance(node, exp.Boolean):
        return _emit_literal_py(bool(node.this), params, prefix + "lit_")

    raise ValueError(f"where_sql: unsupported syntax ({type(node).__name__})")


def _reject_dangerous(tree: Any, exp: Any) -> None:
    # Note: sqlglot ``And`` / ``Or`` subclass ``Func`` — do not ban ``Func`` wholesale.
    for cls in (
        exp.Select,
        exp.Subquery,
        exp.Union,
        exp.Insert,
        exp.Delete,
        exp.Update,
        exp.Anonymous,
        exp.Window,
    ):
        if tree.find(cls):
            raise ValueError(f"where_sql: {cls.__name__} is not allowed")


def compile_where_sql_fragment(expr_text: str, params: dict[str, object], *, prefix: str = "ws_") -> str:
    """
    Parse a single boolean expression and append bound parameters to ``params``.

    Returns a ClickHouse fragment (no ``WHERE`` keyword) using ``{{name:Type}}`` placeholders.
    """
    _, exp = _require_sqlglot()
    import sqlglot

    text = expr_text.strip()
    if not text:
        raise ValueError("where_sql is empty")
    if len(text) > _MAX_LEN:
        raise ValueError(f"where_sql exceeds max length {_MAX_LEN}")

    tree = sqlglot.parse_one(text, read="clickhouse")
    _reject_dangerous(tree, exp)

    return _emit(tree, params, prefix, 0, exp)
