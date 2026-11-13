from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..sql_script import split_sql_statements

try:
    import sqlglot
    from sqlglot import exp

    _HAS_SQLGLOT = True
except Exception:  # pragma: no cover
    sqlglot = None  # type: ignore[assignment]
    exp = None  # type: ignore[assignment]
    _HAS_SQLGLOT = False

from .math import sqlglot_to_latex
from .constraints import extract_expression_caveats


@dataclass(frozen=True)
class LineageRef:
    table_alias: str | None
    column: str


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _strip_leading_sql_comments(sql_text: str) -> str:
    s = sql_text
    while True:
        s2 = s.lstrip()
        if s2.startswith("--"):
            nl = s2.find("\n")
            if nl == -1:
                return ""
            s = s2[nl + 1 :]
            continue
        if s2.startswith("/*"):
            end = s2.find("*/")
            if end == -1:
                return s2
            s = s2[end + 2 :]
            continue
        return s2


def _view_shape_to_insert(sql_text: str) -> str | None:
    """Translate ``CREATE VIEW xform_* (cols) COMMENT '<json>' AS <body>`` into
    the equivalent ``INSERT INTO <target> (cols) <body>`` text so the existing
    insert-transform lineage pipeline applies unchanged. Returns None for
    non-view files.
    """
    s = _strip_leading_sql_comments(sql_text)
    head = re.match(
        r"(?is)^CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)",
        s,
    )
    if not head:
        return None
    rest = s[head.end() :]

    columns: list[str] | None = None
    rest_l = rest.lstrip()
    if rest_l.startswith("("):
        depth = 0
        for i, ch in enumerate(rest_l):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    raw = rest_l[1:i]
                    columns = [
                        c
                        for c in (
                            re.sub(r"--[^\n]*", "", item).strip()
                            for item in raw.split(",")
                        )
                        if c
                    ]
                    rest = rest_l[i + 1 :]
                    break

    m_comment = re.search(r"(?is)\bCOMMENT\s+'((?:[^']|'')*)'", rest)
    target: str | None = None
    if m_comment:
        try:
            cfg = json.loads(m_comment.group(1).replace("''", "'"))
            t = cfg.get("target")
            if isinstance(t, str) and t:
                target = t.split(".")[-1]
        except Exception:
            target = None

    m_as = re.search(r"(?i)\bAS\b", rest)
    if not m_as or not target:
        return None
    body = rest[m_as.end() :].strip()
    if not body:
        return None
    cols = f"({', '.join(columns)})" if columns else ""
    return f"INSERT INTO {target} {cols}\n{body}"


def _parse_transform_target(sql_text: str) -> str | None:
    # View-shape transforms carry the target in the COMMENT JSON.
    insert_form = _view_shape_to_insert(sql_text)
    if insert_form is not None:
        m = re.search(r"(?i)\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\b", insert_form)
        return m.group(1).strip() if m else None
    # Prefer @transform-config header, else fall back to INSERT INTO <table>.
    m = re.search(r"(?mi)^--\s*target\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", sql_text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?i)\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql_text)
    if m:
        return m.group(1).strip()
    return None


def _extract_screener_data_select_block(sql_text: str) -> tuple[str, str] | None:
    """
    Heuristic extractor for transforms shaped like daily_screener:

        WITH screener_data AS ( SELECT ... FROM (...) dm ... )

    Returns (select_list_sql, from_and_joins_sql).
    """
    m = re.search(r"(?is)\bWITH\b.*?\bscreener_data\s+AS\s*\(\s*SELECT\s+(.*)", sql_text)
    if not m:
        return None
    tail = m.group(1)
    # split at the first FROM that starts a line (avoids matching "from" in strings)
    m2 = re.search(r"(?im)^FROM\b", tail)
    if not m2:
        return None
    select_part = tail[: m2.start()]
    from_part = tail[m2.start() :]
    return select_part.strip(), from_part.strip()


def _build_alias_to_source_table(from_sql: str) -> dict[str, str]:
    """
    Build a best-effort mapping like { 'dm': 'daily_metrics', 'dmd': 'daily_metrics_derived', ... }
    by looking for patterns:

        FROM ( ... FROM <table> ... ) <alias>
        LEFT JOIN ( ... FROM <table> ... ) <alias>
        LEFT JOIN (<table> ...) <alias>   (rare)
    """
    alias_to_table: dict[str, str] = {}
    skip_alias = {"final", "where", "on", "using", "join", "left", "inner", "right", "from", "select"}

    # subquery-based aliases: find each ") <alias> \n ON|USING" and backtrack to locate the table.
    for m in re.finditer(r"(?im)\)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\n|\r\n?)\s*(ON|USING)\b", from_sql):
        alias = m.group(1)
        if alias.lower() in skip_alias:
            continue
        # backtrack to the join keyword that introduced this subquery
        head = from_sql[: m.start()]
        join_starts = list(
            re.finditer(
                r"(?im)\b(?:FROM|JOIN|LEFT\s+JOIN|INNER\s+JOIN|RIGHT\s+JOIN)\s*\(",
                head,
            )
        )
        if not join_starts:
            continue
        j = join_starts[-1].start()
        sub = from_sql[j:m.start()]
        from_matches = list(re.finditer(r"(?im)\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b", sub))
        if not from_matches:
            continue
        table = from_matches[-1].group(1)
        alias_to_table.setdefault(alias, table)

    # FROM-subquery alias (no ON right after, typically followed by JOIN ...)
    for m in re.finditer(
        r"(?im)\)\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\n|\r\n?)\s*(JOIN|LEFT\s+JOIN|INNER\s+JOIN|RIGHT\s+JOIN)\b",
        from_sql,
    ):
        alias = m.group(1)
        if alias.lower() in skip_alias or alias in alias_to_table:
            continue
        head = from_sql[: m.start()]
        join_starts = list(
            re.finditer(
                r"(?im)\b(?:FROM|JOIN|LEFT\s+JOIN|INNER\s+JOIN|RIGHT\s+JOIN)\s*\(",
                head,
            )
        )
        if not join_starts:
            continue
        j = join_starts[-1].start()
        sub = from_sql[j:m.start()]
        from_matches = list(re.finditer(r"(?im)\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b", sub))
        if not from_matches:
            continue
        table = from_matches[-1].group(1)
        alias_to_table.setdefault(alias, table)

    # direct table matches: (FROM|JOIN) <table> [FINAL] [AS alias | alias].
    # The optional alias term is guarded against SQL continuation keywords so a
    # bare "x JOIN y" / "x LEFT JOIN y" cannot swallow the next table keyword
    # as an alias of x.
    _alias_guard = (
        r"(?!FINAL\b|JOIN\b|ON\b|WHERE\b|GROUP\b|ORDER\b|LIMIT\b|HAVING\b|"
        r"UNION\b|INNER\b|LEFT\b|RIGHT\b|FULL\b|CROSS\b|USING\b)"
    )
    table_pattern = re.compile(
        r"(?im)\b(?:FROM|(?:LEFT\s+|RIGHT\s+|INNER\s+|FULL\s+|CROSS\s+)?JOIN)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)"
        r"(?:\s+FINAL)?"
        r"(?:\s+" + _alias_guard + r"(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?"
    )
    for m in table_pattern.finditer(from_sql):
        tbl = m.group(1)
        alias = m.group(2)
        if tbl.lower() in skip_alias:
            continue
        alias_to_table.setdefault(tbl, tbl)
        if alias and alias.lower() in skip_alias:
            alias = None
        if alias:
            alias_to_table.setdefault(alias, tbl)
        if "" not in alias_to_table:
            alias_to_table[""] = tbl

    return alias_to_table


def _extract_last_select_before_ranked_data(sql_text: str) -> str | None:
    """
    Extract the final SELECT list feeding `FROM ranked_data`.
    """
    matches = list(re.finditer(r"(?is)\bSELECT\s+(.*?)\bFROM\s+ranked_data\b", sql_text))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def _extract_final_select_list(sql_text: str) -> str | None:
    """
    Extract the SELECT list for the final query:
      SELECT ... FROM ranked_data;

    We anchor to the last occurrence, then keep only the part after the
    "ranked_data AS (...)" CTE marker to avoid accidentally returning screener_data.
    """
    # Start searching after ranked_data is declared, then require the ") SELECT" that closes the CTE.
    anchor = re.search(r"(?is)\branked_data\s+AS\s*\(", sql_text)
    search = sql_text[anchor.end() :] if anchor else sql_text

    matches = list(re.finditer(r"(?is)\)\s*SELECT\s+(.*?)\bFROM\s+ranked_data\b", search))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def _extract_final_select_items(sql_text: str) -> list[str]:
    """
    The transform has two SELECTs that mention `FROM ranked_data`:
      - inside ranked_data CTE (FROM screener_data)
      - final query (FROM ranked_data)

    We reliably grab the last FROM ranked_data match, then split its select list.
    """
    final_select = _extract_final_select_list(sql_text)
    if not final_select:
        return []
    final_select = re.sub(r"(?m)--.*$", "", final_select).strip()
    items = [i for i in _split_select_items(final_select) if i.strip()]
    return items


def _extract_ranked_data_select_block(sql_text: str) -> str | None:
    """
    Extract the SELECT list inside:
      ranked_data AS ( SELECT ... FROM screener_data )
    """
    m = re.search(r"(?is)\branked_data\s+AS\s*\(\s*SELECT\s+(.*)", sql_text)
    if not m:
        return None
    tail = m.group(1)
    m2 = re.search(r"(?im)^FROM\s+screener_data\b", tail)
    if not m2:
        return None
    return tail[: m2.start()].strip()


def _is_simple_identifier(expr_sql: str) -> bool:
    s = expr_sql.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].strip()
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$", s))


def _build_stage_map(select_sql: str) -> dict[str, dict[str, Any]]:
    """
    Build {output_column: {"expression": <sql>, "sources": [...]}} for a SELECT list.
    """
    items = [i for i in _split_select_items(select_sql) if i.strip()]
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        parsed = _parse_select_item(item)
        if parsed is None:
            continue
        out_name, expr_sql = parsed
        out[out_name] = {"expression": expr_sql}
    return out


def _sources_for_expr(expr_sql: str, alias_to_table: dict[str, str]) -> list[dict[str, str]]:
    refs = _extract_refs(expr_sql)
    sources: list[dict[str, str]] = []
    default_tbl = alias_to_table.get("")
    if not default_tbl and len(alias_to_table) == 1:
        default_tbl = next(iter(alias_to_table.values()))

    for r in refs:
        if r.table_alias and r.table_alias in alias_to_table:
            sources.append({"table": alias_to_table[r.table_alias], "column": r.column, "via": r.table_alias})
        elif (not r.table_alias) and ("." in r.column):
            pseudo_table, pseudo_col = r.column.split(".", 1)
            if pseudo_table in alias_to_table:
                sources.append({"table": alias_to_table[pseudo_table], "column": pseudo_col, "via": pseudo_table})
            else:
                sources.append({"table": "", "column": r.column, "via": ""})
                sources.append({"table": default_tbl or "", "column": r.column, "via": ""})
        else:
            sources.append({"table": "", "column": r.column, "via": r.table_alias or ""})
            sources.append({"table": default_tbl or "", "column": r.column, "via": r.table_alias or ""})
    return sources


def _sources_for_expr_expand_ctes(
    expr_sql: str,
    *,
    alias_to_table: dict[str, str],
    default_from: str | None,
    local_output_expr: dict[str, str] | None,
    cte_output_expr: dict[str, dict[str, str]],
    cte_alias_to_table: dict[str, dict[str, str]],
    cte_default_from: dict[str, str | None],
    max_depth: int = 5,
) -> list[dict[str, str]]:
    """
    Expand references that point to CTEs (via alias_to_table) into their underlying sources.
    """
    out: list[dict[str, str]] = []

    def add_sources_for(
        expr: str,
        *,
        a2t: dict[str, str],
        depth: int,
        default_from_name: str | None,
        local_out: dict[str, str] | None,
    ) -> None:
        for r in _extract_refs(expr):
            if not r.table_alias:
                # sqlglot sometimes produces a quoted identifier like "dm.open" rather than a Column(table="dm", name="open").
                if "." in r.column:
                    pseudo_table, pseudo_col = r.column.split(".", 1)
                    mapped = a2t.get(pseudo_table)
                    if mapped:
                        if mapped in cte_output_expr and depth > 0 and pseudo_col in cte_output_expr[mapped]:
                            add_sources_for(
                                cte_output_expr[mapped][pseudo_col],
                                a2t=cte_alias_to_table.get(mapped, {}),
                                depth=depth - 1,
                                default_from_name=cte_default_from.get(mapped),
                                local_out=cte_output_expr.get(mapped),
                            )
                        else:
                            out.append({"table": mapped, "column": pseudo_col, "via": pseudo_table})
                        continue
                # Prefer resolving to a computed column in the current SELECT/CTE (avoid self-referential loop).
                if local_out and r.column in local_out and local_out[r.column].strip() != r.column.strip() and depth > 0:
                    add_sources_for(
                        local_out[r.column],
                        a2t=a2t,
                        depth=depth - 1,
                        default_from_name=default_from_name,
                        local_out=local_out,
                    )
                    continue
                # Otherwise, if this SELECT reads from a single source, attribute to that source.
                if default_from_name:
                    mapped_from = default_from_name
                    # If the FROM itself is a CTE, expand it.
                    if mapped_from in cte_output_expr and r.column in cte_output_expr[mapped_from] and depth > 0:
                        add_sources_for(
                            cte_output_expr[mapped_from][r.column],
                            a2t=cte_alias_to_table.get(mapped_from, {}),
                            depth=depth - 1,
                            default_from_name=cte_default_from.get(mapped_from),
                            local_out=cte_output_expr.get(mapped_from),
                        )
                        continue
                    out.append({"table": mapped_from, "column": r.column, "via": ""})
                    continue
                out.append({"table": "", "column": r.column, "via": ""})
                continue
            mapped = a2t.get(r.table_alias)
            if not mapped:
                out.append({"table": "", "column": r.column, "via": r.table_alias})
                continue

            if mapped in cte_output_expr and depth > 0:
                inner_expr = cte_output_expr[mapped].get(r.column)
                if inner_expr:
                    add_sources_for(
                        inner_expr,
                        a2t=cte_alias_to_table.get(mapped, {}),
                        depth=depth - 1,
                        default_from_name=cte_default_from.get(mapped),
                        local_out=cte_output_expr.get(mapped),
                    )
                else:
                    out.append({"table": mapped, "column": r.column, "via": r.table_alias})
            else:
                out.append({"table": mapped, "column": r.column, "via": r.table_alias})

    add_sources_for(
        expr_sql,
        a2t=alias_to_table,
        depth=max_depth,
        default_from_name=default_from,
        local_out=local_output_expr,
    )

    # deterministically sort & de-dupe
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for s in sorted(out, key=lambda x: (x.get("table", ""), x.get("column", ""), x.get("via", ""))):
        k = (s.get("table", ""), s.get("column", ""), s.get("via", ""))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(s)
    return deduped


def _trace_expr_through_ctes(
    *,
    output_column: str,
    final_expr: str,
    ranked_map: dict[str, dict[str, Any]],
    screener_map: dict[str, dict[str, Any]],
    alias_to_table: dict[str, str],
) -> dict[str, Any]:
    """
    Trace an output column backward through:
      final_select -> ranked_data -> screener_data

    Returns a dict with "expression", "sources", and "steps".
    """
    steps: list[dict[str, Any]] = []

    cur_expr = final_expr.strip()
    steps.append(
        {
            "cte": "final_select",
            "output_column": output_column,
            "expression": cur_expr,
            "sources": _sources_for_expr(cur_expr, alias_to_table),
        }
    )

    # ranked_data lookup by identifier (up to 2 hops)
    for _ in range(2):
        ranked_key = ""
        if _is_simple_identifier(cur_expr):
            ranked_key = cur_expr.strip()
            if len(ranked_key) >= 2 and ranked_key[0] == '"' and ranked_key[-1] == '"':
                ranked_key = ranked_key[1:-1].strip()
        if not ranked_key or ranked_key not in ranked_map:
            break
        ranked_expr = str(ranked_map[ranked_key]["expression"]).strip()
        steps.append(
            {
                "cte": "ranked_data",
                "output_column": output_column,
                "expression": ranked_expr,
                "sources": _sources_for_expr(ranked_expr, alias_to_table),
            }
        )
        if ranked_expr == cur_expr:
            break
        cur_expr = ranked_expr

    # screener_data lookup by identifier
    screener_key = ""
    if _is_simple_identifier(cur_expr):
        screener_key = cur_expr.strip()
        if len(screener_key) >= 2 and screener_key[0] == '"' and screener_key[-1] == '"':
            screener_key = screener_key[1:-1].strip()
    if screener_key and screener_key in screener_map:
        screener_expr = str(screener_map[screener_key]["expression"]).strip()
        steps.append(
            {
                "cte": "screener_data",
                "output_column": output_column,
                "expression": screener_expr,
                "sources": _sources_for_expr(screener_expr, alias_to_table),
            }
        )
        cur_expr = screener_expr

    return {"expression": steps[0]["expression"], "sources": steps[0]["sources"], "steps": steps}

def _extract_insert_column_list(sql_text: str, *, table: str) -> list[str] | None:
    tbl_pat = rf"(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(table)}"
    m = re.search(rf"(?is)\bINSERT\s+INTO\s+{tbl_pat}\s*\((.*?)\)\s*WITH\b", sql_text)
    if not m:
        # Some transforms have no WITH.
        m2 = re.search(rf"(?is)\bINSERT\s+INTO\s+{tbl_pat}\s*\((.*?)\)\s*SELECT\b", sql_text)
        if not m2:
            return None
        block = m2.group(1)
        block = re.sub(r"(?m)--.*$", "", block)
        cols = re.findall(r"`([^`]+)`", block)
        if cols:
            return [c.strip() for c in cols if c.strip()]
        # unquoted
        cols2 = [c.strip() for c in block.split(",") if c.strip()]
        return cols2
    block = m.group(1)
    block = re.sub(r"(?m)--.*$", "", block)
    cols = re.findall(r"`([^`]+)`", block)
    if cols:
        return [c.strip() for c in cols if c.strip()]
    # unquoted column list
    cols2 = [c.strip() for c in block.split(",") if c.strip()]
    return cols2


def _extract_final_select_list_generic(sql_text: str) -> str | None:
    """
    Best-effort extractor for the final SELECT list in a transform shaped like:
      INSERT INTO <target>(...) [WITH ...] SELECT <list> FROM ...
    Returns the <list> portion.
    """
    # Locate the final top-level SELECT and then find the top-level FROM that matches it,
    # so nested subqueries ("FROM" inside expressions) don't truncate the select list.
    ins = re.search(r"(?is)\bINSERT\s+INTO\b", sql_text)
    if not ins:
        return None

    # Start scanning after INSERT INTO (and optional column list).
    start_idx = ins.end()
    m_cols_with = re.search(r"(?is)\bINSERT\s+INTO\b.*?\)\s*WITH\b", sql_text)
    if m_cols_with:
        start_idx = m_cols_with.end()
    else:
        m_cols_select = re.search(r"(?is)\bINSERT\s+INTO\b.*?\)\s*SELECT\b", sql_text)
        if m_cols_select:
            start_idx = m_cols_select.start()

    s = sql_text[start_idx:]

    def is_word_at(i: int, w: str) -> bool:
        return s[i : i + len(w)].upper() == w

    # Find all top-level SELECT starts (depth==0) and take the last one (final query).
    in_squote = False
    in_btick = False
    depth = 0
    selects: list[int] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_btick:
            in_squote = not in_squote
            i += 1
            continue
        if ch == "`" and not in_squote:
            in_btick = not in_btick
            i += 1
            continue
        if in_squote or in_btick:
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and is_word_at(i, "SELECT"):
            before = s[i - 1] if i > 0 else " "
            after = s[i + 6] if i + 6 < len(s) else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                selects.append(i)
            i += 6
            continue
        i += 1

    if not selects:
        return None

    sel_start = selects[-1] + 6  # after SELECT

    # Find top-level FROM after this SELECT.
    in_squote = False
    in_btick = False
    depth = 0
    i = sel_start
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_btick:
            in_squote = not in_squote
            i += 1
            continue
        if ch == "`" and not in_squote:
            in_btick = not in_btick
            i += 1
            continue
        if in_squote or in_btick:
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and is_word_at(i, "FROM"):
            before = s[i - 1] if i > 0 else " "
            after = s[i + 4] if i + 4 < len(s) else " "
            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                return s[sel_start:i].strip()
        i += 1

    return None


def _extract_first_insert_statement(sql_text: str) -> str | None:
    """
    Extract the first top-level INSERT ... ; statement from a transform file.
    This avoids trailing verification SELECTs / helper queries.
    """
    ins = re.search(r"(?is)\bINSERT\s+INTO\b", sql_text)
    if not ins:
        return None
    s = sql_text[ins.start() :]
    in_squote = False
    in_btick = False
    depth = 0
    for i, ch in enumerate(s):
        if ch == "'" and not in_btick:
            in_squote = not in_squote
            continue
        if ch == "`" and not in_squote:
            in_btick = not in_btick
            continue
        if in_squote or in_btick:
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if ch == ";" and depth == 0:
            return s[: i + 1]
    # If no semicolon, return remainder
    return s


def _extract_final_from_name_generic(sql_text: str) -> str | None:
    """
    Extract the FROM name for the final SELECT feeding the INSERT (best effort).
    """
    m_with = re.search(r"(?is)\bINSERT\s+INTO\b.*?\)\s*WITH\b", sql_text)
    if m_with:
        tail = sql_text[m_with.end() :]
        matches = list(re.finditer(r"(?is)\)\s*SELECT\s+.*?\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b", tail))
        if matches:
            return matches[-1].group(1)
    matches = list(re.finditer(r"(?is)\bSELECT\s+.*?\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql_text))
    if not matches:
        return None
    return matches[-1].group(1)


def _extract_cte_select_list(sql_text: str, cte_name: str) -> str | None:
    """
    Extract SELECT list from a simple CTE:  name AS ( SELECT ... FROM ... )
    """
    m = re.search(rf"(?is)\b{re.escape(cte_name)}\s+AS\s*\(\s*SELECT\s+(.*)", sql_text)
    if not m:
        return None
    tail = m.group(1)
    m2 = re.search(r"(?im)^FROM\b", tail)
    if not m2:
        return None
    return tail[: m2.start()].strip()


def _sqlglot_sanitize_params(sql_text: str) -> str:
    """
    Replace ClickHouse parameter placeholders like:
      {chunk_start_date:String}
    with a neutral literal so sqlglot can parse the SQL.
    """
    return re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*:[A-Za-z0-9_()'./]+\}", "0", sql_text)


def _sqlglot_first_insert(sql_text: str) -> exp.Insert | None:
    if not _HAS_SQLGLOT:
        return None
    sanitized = _sqlglot_sanitize_params(sql_text)
    try:
        statements = sqlglot.parse(sanitized, read="clickhouse")
    except Exception:
        return None
    for st in statements:
        ins = st.find(exp.Insert)
        if ins is not None:
            return ins
    return None


def _sqlglot_select_output_map(sel: exp.Select) -> dict[str, str]:
    """
    Map output column name -> expression SQL.
    """
    out: dict[str, str] = {}
    for e in sel.expressions:
        if isinstance(e, exp.Alias):
            out[e.alias] = e.this.sql(dialect="clickhouse")
        elif isinstance(e, exp.Column):
            # Prefer the bare output column name (CTEs often project columns without alias).
            out[e.name] = e.sql(dialect="clickhouse")
        elif isinstance(e, exp.Star):
            out["*"] = "*"
        else:
            # If sqlglot can't name it, skip.
            continue
    return out


def _sqlglot_select_projection_exprs(sel: exp.Select) -> list[str]:
    """
    Return the projection expressions (SQL) in order, suitable for pairing with
    INSERT column list by position.
    """
    exprs: list[str] = []
    for e in sel.expressions:
        if isinstance(e, exp.Alias):
            s = e.this.sql(dialect="clickhouse")
        else:
            s = e.sql(dialect="clickhouse")
        # strip /* ... */ comments that sqlglot may preserve in identifier SQL
        s = re.sub(r"/\\*.*?\\*/", "", s, flags=re.S).strip()
        exprs.append(s)
    return exprs


def _sqlglot_cte_selects_from_with(w: exp.With | None) -> dict[str, exp.Select]:
    out: dict[str, exp.Select] = {}
    if not isinstance(w, exp.With):
        return out
    for c in w.find_all(exp.CTE):
        name = c.alias
        q = c.this
        if isinstance(q, exp.Subquery):
            q = q.this
        if isinstance(q, exp.Select):
            out[name] = q
    return out


def _sqlglot_cte_selects_from_select(sel: exp.Select) -> dict[str, exp.Select]:
    w = sel.args.get("with") or sel.args.get("with_")
    return _sqlglot_cte_selects_from_with(w)  # type: ignore[arg-type]


def _sqlglot_from_single_name(sel: exp.Select) -> str | None:
    """
    If the SELECT reads from a single table/cte name (no schema), return its name.
    """
    frm = sel.args.get("from") or sel.args.get("from_")
    if not isinstance(frm, exp.From):
        return None
    first = None
    if frm.expressions:
        first = frm.expressions[0]
    else:
        first = frm.this
    if first is None:
        return None
    while hasattr(first, "this") and not isinstance(first, (exp.Table, exp.Identifier)):
        first = first.this
    if isinstance(first, exp.Table):
        return first.name
    if isinstance(first, exp.Identifier):
        return first.name
    return None


def _sqlglot_alias_to_table(sel: exp.Select) -> dict[str, str]:
    """
    Best-effort map of alias -> table name for direct FROM/JOIN tables in this SELECT.
    """
    if not _HAS_SQLGLOT:
        return {}
    out: dict[str, str] = {}
    for t in sel.find_all(exp.Table):
        name = t.name
        alias = t.alias
        if alias:
            out.setdefault(alias, name)
    return out


def _sqlglot_select_alias_to_table(sel: exp.Select) -> dict[str, str]:
    """
    Best-effort map of table-alias -> table/CTE name from FROM/JOINs.
    Includes the unaliased table name as its own alias.
    """
    if not _HAS_SQLGLOT:
        return {}
    out: dict[str, str] = {}
    for t in sel.find_all(exp.Table):
        name = t.name
        alias = t.alias or name
        if alias:
            out.setdefault(alias, name)
    return out


def _sqlglot_insert_columns(ins: exp.Insert) -> list[str]:
    cols: list[str] = []
    cols_exp = ins.this
    if isinstance(cols_exp, exp.Schema):
        for c in cols_exp.expressions:
            # ClickHouse INSERT (col list) parses as identifiers/columns, not ColumnDef.
            if isinstance(c, exp.Column):
                cols.append(c.name)
            elif isinstance(c, exp.Identifier):
                cols.append(c.name)
    return cols


def _sqlglot_insert_query(ins: exp.Insert) -> exp.Select | None:
    q = ins.expression
    if isinstance(q, exp.Subquery):
        q = q.this
    return q if isinstance(q, exp.Select) else None


def _trace_identifier_through_output_maps(
    start_ident: str,
    *,
    maps: dict[str, dict[str, str]],
    chain: list[str],
    max_hops: int = 6,
) -> list[tuple[str, str]]:
    """
    Given a starting identifier, follow it through named projection maps.
    Returns [(stage_name, expr_sql), ...] in order.
    """
    cur = start_ident
    out: list[tuple[str, str]] = []
    for stage in chain:
        mp = maps.get(stage)
        if not mp:
            break
        expr = mp.get(cur)
        if expr is None:
            break
        out.append((stage, expr))
        if expr == cur:
            break
        if not _is_simple_identifier(expr):
            break
        cur = expr
        max_hops -= 1
        if max_hops <= 0:
            break
    return out


def generate_lineage_for_insert_transform(
    sql_path: Path,
    repo_root: Path | None = None,
    *,
    sql_text: str | None = None,
) -> dict[str, Any] | None:
    """
    Generic lineage generator for INSERT INTO ... SELECT transforms (single-statement files).
    """
    full_text = sql_text if sql_text is not None else _read_text(sql_path)
    # CREATE VIEW xform_* files parse through the equivalent INSERT-shaped text.
    view_insert = _view_shape_to_insert(full_text)
    if view_insert is not None:
        full_text = view_insert
    sql_text = _extract_first_insert_statement(full_text) or full_text
    target = _parse_transform_target(full_text)
    if not target:
        return None

    # Normalize target for INSERT parsing when the file uses schema-qualified names (e.g. vera.table).
    target = target.split(".")[-1]

    # Artifacts are checkout-portable: store the transform path repo-relative so
    # --check byte-compares cleanly across machines/worktrees/CI.
    rel_sql = (
        sql_path.relative_to(repo_root).as_posix()
        if repo_root is not None and sql_path.is_relative_to(repo_root)
        else sql_path.as_posix()
    )

    # Prefer sqlglot parsing for complex transforms (WITH chains, nested FROMs, etc.).
    # If sqlglot parsing fails or is incomplete for a file, fall back to regex mode.
    if _HAS_SQLGLOT:
        try:
            ins = _sqlglot_first_insert(full_text)
            if ins is not None:
                q = _sqlglot_insert_query(ins)
                if q is not None:
                    insert_cols = _sqlglot_insert_columns(ins)
                    final_exprs = _sqlglot_select_projection_exprs(q)
                    if final_exprs:
                        # Handle SELECT *: expand to INSERT columns if provided.
                        if final_exprs == ["*"] and insert_cols:
                            final_exprs = list(insert_cols)
                        if insert_cols and len(insert_cols) == len(final_exprs):
                            alias_to_table = _sqlglot_alias_to_table(q)
                            ctes = _sqlglot_cte_selects_from_select(q)
                            cte_exprs: dict[str, list[str]] = {
                                name: _sqlglot_select_projection_exprs(sel) for name, sel in ctes.items()
                            }
                            cte_output_expr: dict[str, dict[str, str]] = {
                                name: _sqlglot_select_output_map(sel) for name, sel in ctes.items()
                            }
                            cte_alias_to_table: dict[str, dict[str, str]] = {
                                name: _sqlglot_select_alias_to_table(sel) for name, sel in ctes.items()
                            }
                            cte_default_from: dict[str, str | None] = {
                                name: _sqlglot_from_single_name(sel) for name, sel in ctes.items()
                            }

                            from_name = _sqlglot_from_single_name(q)

                            columns: dict[str, Any] = {}
                            for idx, out_name in enumerate(insert_cols):
                                expr_sql = final_exprs[idx]
                                srcs = _sources_for_expr_expand_ctes(
                                    expr_sql,
                                    alias_to_table=alias_to_table,
                                    default_from=from_name,
                                    local_output_expr=None,
                                    cte_output_expr=cte_output_expr,
                                    cte_alias_to_table=cte_alias_to_table,
                                    cte_default_from=cte_default_from,
                                )
                                steps: list[dict[str, Any]] = [
                                    {
                                        "cte": "final_select",
                                        "output_column": out_name,
                                        "expression": expr_sql,
                                        "sources": srcs,
                                    }
                                ]
                                # Common pattern: final SELECT reads from a single CTE/table and projects bare identifiers.
                                if from_name and from_name in cte_exprs and _is_simple_identifier(expr_sql):
                                    # Try to look up by position when possible.
                                    # If the identifier matches a column name projected by the CTE, capture expression.
                                    # Otherwise, skip.
                                    cte_sel_map = _sqlglot_select_output_map(ctes[from_name])
                                    if expr_sql in cte_sel_map:
                                        cexpr = cte_sel_map[expr_sql]
                                        steps.append(
                                            {
                                                "cte": from_name,
                                                "output_column": out_name,
                                                "expression": cexpr,
                                                "sources": _sources_for_expr_expand_ctes(
                                                    cexpr,
                                                    alias_to_table=cte_alias_to_table.get(from_name, {}),
                                                    default_from=cte_default_from.get(from_name),
                                                    local_output_expr=cte_output_expr.get(from_name),
                                                    cte_output_expr=cte_output_expr,
                                                    cte_alias_to_table=cte_alias_to_table,
                                                    cte_default_from=cte_default_from,
                                                ),
                                            }
                                        )

                                calc_expr = steps[-1]["expression"] if steps else expr_sql
                                latex_expr, math_vars = sqlglot_to_latex(calc_expr)
                                col_caveats = extract_expression_caveats(
                                    calc_expr,
                                    column_name=out_name,
                                    full_query_sql=full_text,
                                )

                                col_entry: dict[str, Any] = {
                                    "expression": steps[0]["expression"],
                                    "sources": steps[0]["sources"],
                                    "steps": steps,
                                }
                                if col_caveats:
                                    col_entry["caveats"] = col_caveats
                                if latex_expr:
                                    col_entry["math"] = {
                                        "latex": latex_expr,
                                        "variables": math_vars,
                                    }
                                columns[out_name] = col_entry

                            return {
                                "version": 2 if (from_name and from_name in ctes) else 1,
                                "target_table": target,
                                "transform_path": rel_sql,
                                "alias_to_table": {k: alias_to_table[k] for k in sorted(alias_to_table)},
                                "columns": {k: columns[k] for k in sorted(columns)},
                            }
        except Exception:
            pass

    # Fallback regex-based parsing for simple transforms.
    final_select = _extract_final_select_list_generic(sql_text)
    if not final_select:
        return None
    final_select = re.sub(r"(?m)--.*$", "", final_select).strip()
    final_items = [i for i in _split_select_items(final_select) if i.strip()]
    insert_cols = _extract_insert_column_list(sql_text, table=target)
    if not insert_cols:
        inferred: list[str] = []
        for item in final_items:
            parsed = _parse_select_item(item)
            inferred.append(parsed[0] if parsed else "")
        if any(not c for c in inferred):
            return None
        insert_cols = inferred
    if len(final_items) != len(insert_cols):
        # Handle SELECT * by tracing into the FROM CTE/table when possible.
        if len(final_items) == 1 and final_items[0].strip() == "*":
            from_name = _extract_final_from_name_generic(sql_text)
            if from_name:
                cte_sel = _extract_cte_select_list(sql_text, from_name)
                if cte_sel:
                    cte_sel = re.sub(r"(?m)--.*$", "", cte_sel).strip()
                    final_items = [i for i in _split_select_items(cte_sel) if i.strip()]
        if len(final_items) != len(insert_cols):
            return None

    # Best-effort alias mapping from the final FROM/JOIN block in the tail.
    m_from = list(re.finditer(r"(?is)\bFROM\b", sql_text))
    from_sql = sql_text[m_from[-1].start() :] if m_from else ""
    alias_to_table = _build_alias_to_source_table(from_sql)

    columns: dict[str, Any] = {}
    for idx, item in enumerate(final_items):
        parsed = _parse_select_item(item)
        if parsed is None:
            continue
        _out_name, expr_sql = parsed
        target_name = insert_cols[idx]
        latex_expr, math_vars = sqlglot_to_latex(expr_sql)
        col_caveats = extract_expression_caveats(
            expr_sql,
            column_name=target_name,
            full_query_sql=sql_text,
        )
        col_entry: dict[str, Any] = {
            "expression": expr_sql,
            "sources": _sources_for_expr(expr_sql, alias_to_table),
            "steps": [
                {
                    "cte": "final_select",
                    "output_column": target_name,
                    "expression": expr_sql,
                    "sources": _sources_for_expr(expr_sql, alias_to_table),
                }
            ],
        }
        if col_caveats:
            col_entry["caveats"] = col_caveats
        if latex_expr:
            col_entry["math"] = {
                "latex": latex_expr,
                "variables": math_vars,
            }
        columns[target_name] = col_entry

    return {
        "version": 1,
        "target_table": target,
        "transform_path": rel_sql,
        "alias_to_table": {k: alias_to_table[k] for k in sorted(alias_to_table)},
        "columns": {k: columns[k] for k in sorted(columns)},
    }


def _split_select_items(select_sql: str) -> list[str]:
    """
    Split a SELECT list into items. We rely on sqlglot for comma handling.
    """
    if _HAS_SQLGLOT:
        parsed = sqlglot.parse_one(f"SELECT {select_sql}", read="clickhouse")
        assert isinstance(parsed, exp.Select)
        return [i.sql(dialect="clickhouse") for i in parsed.expressions]

    # Fallback: split on commas not inside (), '' or ``.
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    in_squote = False
    in_btick = False
    i = 0
    while i < len(select_sql):
        ch = select_sql[i]
        if ch == "'" and not in_btick:
            in_squote = not in_squote
            buf.append(ch)
            i += 1
            continue
        if ch == "`" and not in_squote:
            in_btick = not in_btick
            buf.append(ch)
            i += 1
            continue
        if not in_squote and not in_btick:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                s = "".join(buf).strip()
                if s:
                    items.append(s)
                buf = []
                i += 1
                continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    return items


def _parse_select_item(item_sql: str) -> tuple[str, str] | None:
    """
    Return (output_name, expression_sql) for items like:
      dm.open AS `dm.open`
      close
      now() AS lastupdated

    If output_name can't be determined, returns None.
    """
    if _HAS_SQLGLOT:
        e = sqlglot.parse_one(item_sql, read="clickhouse")
        if isinstance(e, exp.Alias):
            out = e.alias
            expr = e.this.sql(dialect="clickhouse")
            return out, expr
        if isinstance(e, exp.Column):
            return e.sql(dialect="clickhouse"), e.sql(dialect="clickhouse")
        if isinstance(e, exp.Identifier):
            return e.name, e.name
        return None

    # Fallback: handle "<expr> AS `name`" and bare identifiers/columns.
    m = re.match(r"(?is)^(.*?)\s+AS\s+`([^`]+)`\s*$", item_sql.strip())
    if m:
        expr_sql = m.group(1).strip()
        out_name = m.group(2).strip()
        return out_name, expr_sql

    m = re.match(r"(?is)^(.*?)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item_sql.strip())
    if m:
        expr_sql = m.group(1).strip()
        out_name = m.group(2).strip()
        return out_name, expr_sql

    bare = item_sql.strip()
    if bare.startswith("`") and bare.endswith("`") and len(bare) >= 2:
        name = bare[1:-1]
        return name, name
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$", bare):
        return bare, bare
    return None


def _extract_refs(expr_sql: str) -> list[LineageRef]:
    if _HAS_SQLGLOT:
        try:
            node = sqlglot.parse_one(expr_sql, read="clickhouse")
            refs: set[tuple[str | None, str]] = set()
            for c in node.find_all(exp.Column):
                refs.add((c.table or None, c.name))
            return [LineageRef(t, c) for (t, c) in sorted(refs, key=lambda x: (x[0] or "", x[1]))]
        except Exception:
            # Fall back to regex extraction below.
            pass

    # Fallback regex: alias.column
    refs: set[tuple[str | None, str]] = set()
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", expr_sql):
        refs.add((m.group(1), m.group(2)))
    return [LineageRef(t, c) for (t, c) in sorted(refs, key=lambda x: (x[0] or "", x[1]))]


def _json_dumps_deterministic(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def generate_lineage_artifacts(
    repo_root: Path,
    *,
    transforms: Iterable[Path] | None = None,
    out_dir: Path | None = None,
) -> list[Path]:
    """
    Generate lineage artifacts for supported transforms.

    Currently implemented: generic INSERT transform lineage.
    """
    if transforms is None:
        transforms = sorted((repo_root / "sql/schema").glob("*.sql")) + sorted(
            (repo_root / "sql/transform/metrics").glob("[0-9]*-*.sql")
        )
    if out_dir is None:
        out_dir = repo_root / "sql/lineage"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for p in transforms:
        text = _read_text(p)
        statements = split_sql_statements(text)
        managed_views = []
        for statement in statements:
            # Schema scripts may have comments before each statement. Remove
            # only leading comments so the view parser sees the CREATE header.
            candidate = re.sub(
                r"(?s)^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*",
                "",
                statement,
            ).strip()
            if _view_shape_to_insert(candidate) is not None:
                managed_views.append(candidate)
        candidates = managed_views or ([text] if not p.parent.name == "schema" else [])
        for candidate in candidates:
            target = _parse_transform_target(candidate)
            if not target:
                continue
            artifact = generate_lineage_for_insert_transform(
                p, repo_root, sql_text=candidate
            )
            if artifact is None:
                continue
            out_path = out_dir / f"{artifact['target_table']}.json"
            out_path.write_text(_json_dumps_deterministic(artifact), encoding="utf-8")
            written.append(out_path)
    return written
