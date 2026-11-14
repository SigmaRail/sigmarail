"""Compile ``query_table_v1`` ``spec.sql`` against the MCP exposure catalog.

Parse with sqlglot (ClickHouse dialect), allowlist catalog tables and AS prefixes,
rewrite LEFT JOIN → LEFT ANY, inject FINAL + clamped LIMIT. Does not push date
predicates. The agent string is never sent to ClickHouse unchanged.
"""

from __future__ import annotations

import os
import re
from typing import Any

from sigmarail.features.mcp_table_catalog import (
    CatalogEntry,
    prefix_to_entry,
    table_to_entry,
)

_MAX_SQL_LEN = 8192
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _require_sqlglot():  # type: ignore[no-untyped-def]
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "spec.sql requires sqlglot (listed in vera install_requires). "
            "Re-install the package: pip install -e ."
        ) from e
    return sqlglot, exp


def _max_rows() -> int:
    return int(os.environ.get("MCP_MAX_ROWS", "500").strip())


def _default_limit() -> int:
    return int(os.environ.get("MCP_DEFAULT_LIMIT", "50").strip())


def _clamp_limit(limit: int | None, max_rows: int | None = None) -> int:
    mx = max_rows if max_rows is not None else _max_rows()
    d = _default_limit()
    v = d if limit is None else int(limit)
    if v < 1:
        v = 1
    return min(v, mx)


def _literal_int(node: Any, exp: Any) -> int | None:
    if node is None:
        return None
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(str(node.this))
        except ValueError:
            return None
    inner = getattr(node, "this", None)
    if inner is not None and inner is not node:
        return _literal_int(inner, exp)
    return None


def _flatten_and(node: Any, exp: Any) -> list[Any]:
    if isinstance(node, exp.And):
        return _flatten_and(node.left, exp) + _flatten_and(node.right, exp)
    return [node]


def _col_ref(node: Any, exp: Any) -> tuple[str, str]:
    if not isinstance(node, exp.Column):
        raise ValueError("JOIN ON must be prefix.column = prefix.column")
    alias = str(node.table or "").strip("`")
    name = str(node.name or "").strip("`")
    if not alias or not _IDENT.match(alias) or not name or not _IDENT.match(name):
        raise ValueError("JOIN ON columns must be qualified prefix.column")
    return alias, name


def _validate_on(on: Any, left_alias: str, right_alias: str, exp: Any) -> None:
    entries = prefix_to_entry()
    if left_alias not in entries or right_alias not in entries:
        raise ValueError("JOIN ON aliases must be catalog prefixes already in FROM/JOIN")
    left_e = entries[left_alias]
    right_e = entries[right_alias]
    if on is None:
        raise ValueError("JOIN requires ON")
    eqs: list[tuple[str, str, str, str]] = []
    for pred in _flatten_and(on, exp):
        if not isinstance(pred, exp.EQ):
            raise ValueError("JOIN ON only allows AND of equalities")
        a_alias, a_col = _col_ref(pred.left, exp)
        b_alias, b_col = _col_ref(pred.right, exp)
        if {a_alias, b_alias} != {left_alias, right_alias}:
            raise ValueError(
                f"JOIN ON must compare {left_alias} and {right_alias} only"
            )
        if a_col != b_col:
            raise ValueError("JOIN ON equalities must use the same column name on both sides")
        eqs.append((a_alias, a_col, b_alias, b_col))
    cols = {e[1] for e in eqs}
    date_key = left_e.time_key
    if date_key != right_e.time_key:
        raise ValueError("JOIN time_key mismatch in catalog")
    if left_e.entity_key is None or right_e.entity_key is None:
        if cols != {date_key}:
            raise ValueError(
                f"JOIN involving {left_alias}/{right_alias} ON must be {date_key} only"
            )
        return
    need = {left_e.entity_key, date_key}
    if cols != need:
        raise ValueError(
            f"JOIN ON must be {left_e.entity_key} and {date_key} "
            f"({left_alias}.{left_e.entity_key} = {right_alias}.{left_e.entity_key} AND "
            f"{left_alias}.{date_key} = {right_alias}.{date_key})"
        )


def _table_alias_entry(table_expr: Any, exp: Any) -> tuple[str, CatalogEntry]:
    if not isinstance(table_expr, exp.Table):
        raise ValueError("FROM/JOIN must be a catalog table, not a subquery or table function")
    name = str(table_expr.name or "").strip("`")
    alias = str(table_expr.alias or "").strip("`")
    by_table = table_to_entry()
    if name not in by_table:
        raise ValueError(f"table {name!r} is not in the vera MCP exposure catalog")
    entry = by_table[name]
    if not alias:
        raise ValueError(f"table {name!r} requires AS {entry.prefix}")
    if alias != entry.prefix:
        raise ValueError(f"table {name!r} must use AS {entry.prefix}, not AS {alias}")
    return alias, entry


def _inject_final(sql: str, alias_tables: dict[str, str]) -> str:
    out = sql
    for prefix, table in alias_tables.items():
        pattern = re.compile(
            rf"\b({re.escape(table)})\s+AS\s+({re.escape(prefix)})\b(?!\s+FINAL\b)",
            flags=re.IGNORECASE,
        )
        out, n = pattern.subn(rf"\1 AS \2 FINAL", out)
        if n < 1:
            raise ValueError(f"could not inject FINAL for {table} AS {prefix}")
    return out


def compile_screener_sql(
    sql_text: str,
    *,
    columns: dict[str, frozenset[str]] | None = None,
    limit_override: int | None = None,
    max_rows: int | None = None,
) -> tuple[str, dict[str, object], dict[str, str]]:
    """Return (clickhouse SQL, parameters, alias→table). Raises ValueError on policy failure."""
    sqlglot, exp = _require_sqlglot()
    text = (sql_text or "").strip()
    if not text:
        raise ValueError("sql is empty")
    if len(text) > _MAX_SQL_LEN:
        raise ValueError(f"sql exceeds max length {_MAX_SQL_LEN}")

    statements = sqlglot.parse(text, read="clickhouse")
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise ValueError("sql must be a single SELECT statement")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise ValueError("sql must be a SELECT")

    banned: list[tuple[Any, str]] = [
        (exp.Insert, "INSERT"),
        (exp.Delete, "DELETE"),
        (exp.Update, "UPDATE"),
        (exp.Drop, "DROP"),
        (exp.Union, "UNION"),
        (exp.Subquery, "subquery"),
        (exp.Window, "window"),
        (exp.Star, "SELECT *"),
    ]
    for attr, label in (
        ("Alter", "ALTER"),
        ("With", "WITH"),
        ("CTE", "CTE"),
        ("TableFromStringOrExpression", "table function"),
    ):
        cls = getattr(exp, attr, None)
        if cls is not None:
            banned.append((cls, label))
    for cls, label in banned:
        if tree.find(cls):
            raise ValueError(f"{label} is not allowed in spec.sql")

    if tree.args.get("with_"):
        raise ValueError("WITH/CTE is not allowed in spec.sql")
    if tree.args.get("settings"):
        raise ValueError("SETTINGS is not allowed in spec.sql")

    from_ = tree.args.get("from_")
    if from_ is None:
        raise ValueError("sql requires FROM")
    from_table = from_.this
    seen: dict[str, CatalogEntry] = {}
    alias, entry = _table_alias_entry(from_table, exp)
    seen[alias] = entry

    joins = list(tree.args.get("joins") or [])
    for join in joins:
        side = str(join.args.get("side") or "").upper()
        kind = str(join.args.get("kind") or "").upper()
        if side != "LEFT":
            raise ValueError("only LEFT ANY JOIN is allowed")
        if kind not in ("", "ANY"):
            raise ValueError("only LEFT ANY JOIN is allowed")
        join.set("kind", "ANY")
        j_alias, j_entry = _table_alias_entry(join.this, exp)
        if j_alias in seen:
            raise ValueError(f"duplicate alias {j_alias!r}")
        on = join.args.get("on")
        if on is None:
            raise ValueError("JOIN requires ON")
        on_aliases: set[str] = set()
        for pred in _flatten_and(on, exp):
            if not isinstance(pred, exp.EQ):
                raise ValueError("JOIN ON only allows AND of equalities")
            a_alias, _a_col = _col_ref(pred.left, exp)
            b_alias, _b_col = _col_ref(pred.right, exp)
            on_aliases.update((a_alias, b_alias))
        if j_alias not in on_aliases or len(on_aliases) != 2:
            raise ValueError(
                f"JOIN {j_alias} ON must compare that alias to exactly one other prefix"
            )
        other = next(iter(on_aliases - {j_alias}))
        if other not in seen:
            raise ValueError(f"JOIN ON references unknown alias {other!r}")
        seen[j_alias] = j_entry
        _validate_on(on, other, j_alias, exp)

    grains = {e.grain for e in seen.values()}
    if len(grains) > 1:
        raise ValueError(f"JOIN grain mismatch: {sorted(grains)}")

    if tree.find(exp.Star):
        raise ValueError("SELECT * is not allowed in spec.sql")

    for col in tree.find_all(exp.Column):
        qual = str(col.table or "").strip("`")
        cname = str(col.name or "").strip("`")
        if joins:
            if not qual or qual not in seen:
                raise ValueError(
                    f"column {cname!r} must be qualified with a JOIN alias "
                    f"({', '.join(sorted(seen))})"
                )
        elif qual and qual not in seen:
            raise ValueError(f"unknown column prefix {qual!r}")
        check_alias = qual if qual else next(iter(seen))
        if columns is not None:
            allowed = columns.get(check_alias)
            if allowed is None or cname not in allowed:
                raise ValueError(
                    f"unknown column {check_alias}.{cname} for catalog table "
                    f"{seen[check_alias].table}"
                )

    lim_expr = tree.args.get("limit")
    if isinstance(lim_expr, exp.Limit):
        lim_expr = lim_expr.args.get("expression")
    current = _literal_int(lim_expr, exp) if lim_expr is not None else None
    if limit_override is not None:
        current = int(limit_override)
    lim = _clamp_limit(current, max_rows=max_rows)
    tree.set("limit", exp.Limit(expression=exp.Literal.number(lim)))
    tree.set("offset", None)

    generated = tree.sql(dialect="clickhouse")
    alias_tables = {p: e.table for p, e in seen.items()}
    generated = _inject_final(generated, alias_tables)
    params: dict[str, object] = {"lim": lim}
    return generated, params, alias_tables
