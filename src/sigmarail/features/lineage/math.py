from __future__ import annotations

import re
from typing import Any

try:
    import sqlglot
    from sqlglot import exp
    _HAS_SQLGLOT = True
except Exception:
    sqlglot = None  # type: ignore[assignment]
    exp = None  # type: ignore[assignment]
    _HAS_SQLGLOT = False


def _escape_latex_text(text: str) -> str:
    """Safely escape all LaTeX/KaTeX active characters."""
    t = str(text)
    t = t.replace("\\", "\\textbackslash{}")
    t = t.replace("_", "\\_")
    t = t.replace("%", "\\%")
    t = t.replace("&", "\\&")
    t = t.replace("^", "\\^{}")
    t = t.replace("#", "\\#")
    t = t.replace("$", "\\$")
    t = t.replace("~", "\\~{}")
    return t


def _clean_symbol(name: str) -> str:
    """Format an identifier into a readable LaTeX math token or macro."""
    s = name.strip().lower()
    s = re.sub(r"/\*.*?\*/", "", name, flags=re.DOTALL).strip().lower()
    symbol_map = {
        "yearly_performance": "P_{1\\text{y}}",
        "perf_1y": "P_{1\\text{y}}",
        "yearly_pct": "P_{1\\text{y}}",
        "performance_6m": "P_{6\\text{m}}",
        "perf_6m": "P_{6\\text{m}}",
        "performance_6m_pct": "P_{6\\text{m}}",
        "performance_3m": "P_{3\\text{m}}",
        "perf_3m": "P_{3\\text{m}}",
        "performance_3m_pct": "P_{3\\text{m}}",
        "performance_1m": "P_{1\\text{m}}",
        "perf_1m": "P_{1\\text{m}}",
        "performance_1m_pct": "P_{1\\text{m}}",
        "blended_pct": "\\text{Score}_{\\text{blended}}",
        "rs_rating": "\\text{RS}",
        "close": "\\text{Close}",
        "spy_close": "\\text{SPY}_{\\text{close}}",
        "volume": "\\text{Volume}",
        "market_cap": "\\text{MarketCap}",
        "net_income": "\\text{NetIncome}",
        "ebitda": "\\text{EBITDA}",
        "sma200d": "\\text{SMA}_{200}",
        "sma150d": "\\text{SMA}_{150}",
        "sma50d": "\\text{SMA}_{50}",
        "sma20d": "\\text{SMA}_{20}",
        "sma10d": "\\text{SMA}_{10}",
        "high_52w": "\\text{High}_{52\\text{w}}",
        "low_52w": "\\text{Low}_{52\\text{w}}",
        "avg_vol_20d": "\\overline{V}_{20\\text{d}}",
        "avg_vol_5d": "\\overline{V}_{5\\text{d}}",
        "avg_vol_90d": "\\overline{V}_{90\\text{d}}",
        "sma200d_slope_20d": "\\text{Slope}_{20}(\\text{SMA}_{200})",
        "sma50d_slope_20d": "\\text{Slope}_{20}(\\text{SMA}_{50})",
        "vcp_consolidation_days_5pct_30d": "\\text{VCP}_{\\text{days}}",
        "vcp_atr_compression_5d_90d": "\\text{ATR}_{\\text{comp}}",
        "vcp_volume_dryup_5d_90d": "\\text{Vol}_{\\text{dryup}}",
        "vcp_proximity_90d": "\\text{Dist}_{\\text{pivot}}",
        "technical_rating": "\\text{Rating}_{\\text{tech}}",
        "setup_quality_rating": "\\text{Rating}_{\\text{setup}}",
    }
    if s in symbol_map:
        return symbol_map[s]
    # Escape underscores for LaTeX text
    escaped = s.replace("_", "\\_")
    return f"\\text{{{escaped}}}"


def _glossary_entry(name: str) -> tuple[str, str] | None:
    s = name.strip().lower()
    mapping = {
        "yearly_performance": ("P_{1\\text{y}}", "1-Year (252-day) lookback performance"),
        "perf_1y": ("P_{1\\text{y}}", "1-Year (252-day) lookback performance"),
        "yearly_pct": ("P_{1\\text{y}}", "Cross-sectional percentile of 1-year performance"),
        "performance_6m": ("P_{6\\text{m}}", "6-Month (126-day) lookback performance"),
        "perf_6m": ("P_{6\\text{m}}", "6-Month (126-day) lookback performance"),
        "performance_6m_pct": ("P_{6\\text{m}}", "Cross-sectional percentile of 6-month performance"),
        "performance_3m": ("P_{3\\text{m}}", "3-Month (63-day) lookback performance"),
        "perf_3m": ("P_{3\\text{m}}", "3-Month (63-day) lookback performance"),
        "performance_3m_pct": ("P_{3\\text{m}}", "Cross-sectional percentile of 3-month performance"),
        "performance_1m": ("P_{1\\text{m}}", "1-Month (21-day) lookback performance"),
        "perf_1m": ("P_{1\\text{m}}", "1-Month (21-day) lookback performance"),
        "performance_1m_pct": ("P_{1\\text{m}}", "Cross-sectional percentile of 1-month performance"),
        "blended_pct": ("\\text{Score}_{\\text{blended}}", "Weighted multi-horizon blended score"),
        "rs_rating": ("\\text{RS}", "Relative Strength Percentile Rating [1-99]"),
        "spy_close": ("\\text{SPY}_{\\text{close}}", "S&P 500 benchmark split-adjusted closing price"),
        "sma200d": ("\\text{SMA}_{200}", "200-day Simple Moving Average"),
        "sma150d": ("\\text{SMA}_{150}", "150-day Simple Moving Average"),
        "sma50d": ("\\text{SMA}_{50}", "50-day Simple Moving Average"),
        "sma20d": ("\\text{SMA}_{20}", "20-day Simple Moving Average"),
        "sma10d": ("\\text{SMA}_{10}", "10-day Simple Moving Average"),
        "high_52w": ("\\text{High}_{52\\text{w}}", "52-Week Rolling Intraday/Close High"),
        "low_52w": ("\\text{Low}_{52\\text{w}}", "52-Week Rolling Intraday/Close Low"),
        "avg_vol_20d": ("\\overline{V}_{20\\text{d}}", "20-day Average Trading Volume"),
        "avg_vol_5d": ("\\overline{V}_{5\\text{d}}", "5-day Average Trading Volume"),
        "avg_vol_90d": ("\\overline{V}_{90\\text{d}}", "90-day Average Trading Volume"),
        "sma200d_slope_20d": ("\\text{Slope}_{20}(\\text{SMA}_{200})", "20-day Linear Slope of 200 SMA"),
        "sma50d_slope_20d": ("\\text{Slope}_{20}(\\text{SMA}_{50})", "20-day Linear Slope of 50 SMA"),
        "vcp_consolidation_days_5pct_30d": ("\\text{VCP}_{\\text{days}}", "Days consolidating within tight 5% bandwidth"),
        "vcp_atr_compression_5d_90d": ("\\text{ATR}_{\\text{comp}}", "5-day ATR divided by 90-day ATR volatility compression"),
        "vcp_volume_dryup_5d_90d": ("\\text{Vol}_{\\text{dryup}}", "Volume Dry-up Ratio (5d avg volume / 90d avg volume)"),
        "vcp_proximity_90d": ("\\text{Dist}_{\\text{pivot}}", "Distance percentage to 90-day consolidation pivot"),
    }
    return mapping.get(s)


def sqlglot_to_latex(ast: Any) -> tuple[str, dict[str, str]]:
    """Convert a sqlglot expression AST or SQL string into a LaTeX equation and variable glossary."""
    if not _HAS_SQLGLOT or ast is None:
        return "", {}

    if isinstance(ast, str):
        # Strip inline SQL comments
        cleaned_ast = re.sub(r"/\*.*?\*/", "", ast, flags=re.DOTALL)
        cleaned_ast = re.sub(r"--.*", "", cleaned_ast).strip()

        # If it is a JSON literal or empty, do not treat as a math formula
        if (
            (cleaned_ast.startswith("{") and cleaned_ast.endswith("}"))
            or (cleaned_ast.startswith("[") and cleaned_ast.endswith("]"))
            or not cleaned_ast
            or "demote_persistence_days" in cleaned_ast
        ):
            return "", {}

        try:
            parsed = sqlglot.parse_one(cleaned_ast, read="clickhouse")
        except Exception:
            clean_sub = _escape_latex_text(cleaned_ast[:60])
            return f"\\text{{{clean_sub}}}", {}
    else:
        parsed = ast

    variables: dict[str, str] = {}

    def _convert(node: Any) -> str:
        if node is None:
            return ""

        # Window function: Percentile Rank pattern:
        # (row_number() OVER (PARTITION BY date ...) - 1) / (count() OVER (...) - 1) * 100
        if isinstance(node, (exp.Mul, exp.Div)):
            sql_rep = node.sql("clickhouse").lower()
            if "row_number()" in sql_rep and "count()" in sql_rep:
                variables["N_t"] = "Total number of active constituent equities on date $t$"
                variables["\\text{Rank}_t(\\cdot)"] = "Ordinal rank across cohort on date $t$ (1 = lowest, $N_t$ = highest)"
                # Check for order by inside row_number
                for win in node.find_all(exp.Window):
                    for ob in win.find_all(exp.Ordered):
                        target_node = ob.this
                        if isinstance(target_node, exp.Coalesce) and target_node.this is not None:
                            target_node = target_node.this
                        target_col = target_node.sql().strip()
                        sym = _clean_symbol(target_col)
                        g = _glossary_entry(target_col)
                        if g:
                            variables[g[0]] = g[1]
                        if "* 100" in sql_rep or isinstance(node, exp.Mul):
                            return f"\\left( \\frac{{\\text{{Rank}}_t({sym}) - 1}}{{N_t - 1}} \\right) \\times 100"
                        return f"\\frac{{\\text{{Rank}}_t({sym}) - 1}}{{N_t - 1}}"

        # Rolling Moving Average pattern:
        # avg(...) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN K PRECEDING ...)
        # ClickHouse Window: PercentRank or rolling SMA
        if isinstance(node, exp.Window):
            win_sql = node.sql("clickhouse").lower()
            if "percent_rank()" in win_sql:
                scope = "cohort"
                if "industry" in win_sql:
                    scope = "industry"
                elif "sector" in win_sql:
                    scope = "sector"
                metric_sym = "\\text{metric}"
                for ob in node.find_all(exp.Ordered):
                    col = ob.this.sql().split(".")[-1].strip("`\"'")
                    metric_sym = _clean_symbol(col)
                    g = _glossary_entry(col)
                    if g:
                        variables[g[0]] = g[1]
                variables[f"\\text{{PercentRank}}_{{t, \\text{{{scope}}}}}"] = f"Cross-sectional percentile rank across {scope} on date $t$"
                return f"\\text{{PercentRank}}_{{t, \\text{{{scope}}}}}\\left({metric_sym}\\right)"

            if "rows between" in win_sql and "preceding" in win_sql:
                m = re.search(r"between\s+(\d+)\s+preceding", win_sql)
                k = int(m.group(1)) + 1 if m else 50
                inner = node.this
                inner_str = _convert(inner)
                variables[f"\\text{{SMA}}_{{{k}}}"] = f"{k}-day rolling simple moving average"
                return f"\\text{{SMA}}_{{{k}}}\\left({inner_str}\\right)"

        # Least / Greatest
        if isinstance(node, exp.Least):
            all_args = ([node.this] if node.this is not None else []) + list(node.expressions or [])
            return f"\\min\\left({', '.join(_convert(a) for a in all_args)}\\right)"

        if isinstance(node, exp.Greatest):
            all_args = ([node.this] if node.this is not None else []) + list(node.expressions or [])
            return f"\\max\\left({', '.join(_convert(a) for a in all_args)}\\right)"

        # Case / When / Then
        if isinstance(node, exp.Case):
            ifs = node.args.get("ifs", [])
            default = node.args.get("default")
            lines = []
            for if_node in ifs:
                cond = _convert(if_node.this)
                then_val = _convert(if_node.args.get("true"))
                lines.append(f"{then_val} & \\text{{if }} {cond}")
            if default is not None:
                lines.append(f"{_convert(default)} & \\text{{otherwise}}")
            return "\\begin{cases} " + " \\\\ ".join(lines) + " \\end{cases}"

        if isinstance(node, exp.If):
            cond = _convert(node.this)
            then_val = _convert(node.args.get("true"))
            else_val = _convert(node.args.get("false"))
            return f"\\begin{{cases}} {then_val} & \\text{{if }} {cond} \\\\ {else_val} & \\text{{otherwise}} \\end{{cases}}"

        # Pattern Matching and Set Membership
        if isinstance(node, (exp.Like, exp.ILike)):
            left = _convert(node.this)
            right = _convert(node.expression)
            op = "\\text{ ILIKE }" if isinstance(node, exp.ILike) else "\\text{ LIKE }"
            return f"{left} {op} {right}"

        if isinstance(node, exp.In):
            left = _convert(node.this)
            items = [_convert(e) for e in (node.expressions or [])]
            return f"{left} \\in \\left( {', '.join(items)} \\right)"

        # Comparisons and Relational Operators
        if isinstance(node, exp.GT):
            return f"{_convert(node.this)} > {_convert(node.expression)}"
        if isinstance(node, exp.GTE):
            return f"{_convert(node.this)} \\ge {_convert(node.expression)}"
        if isinstance(node, exp.LT):
            return f"{_convert(node.this)} < {_convert(node.expression)}"
        if isinstance(node, exp.LTE):
            return f"{_convert(node.this)} \\le {_convert(node.expression)}"
        if isinstance(node, exp.EQ):
            return f"{_convert(node.this)} = {_convert(node.expression)}"
        if isinstance(node, exp.NEQ):
            return f"{_convert(node.this)} \\neq {_convert(node.expression)}"
        if isinstance(node, exp.Between):
            return f"{_convert(node.args.get('low'))} \\le {_convert(node.this)} \\le {_convert(node.args.get('high'))}"
        if isinstance(node, exp.And):
            return f"{_convert(node.this)} \\land {_convert(node.expression)}"
        if isinstance(node, exp.Or):
            return f"{_convert(node.this)} \\lor {_convert(node.expression)}"
        if isinstance(node, exp.Not):
            return f"\\neg \\left({_convert(node.this)}\\right)"
        if isinstance(node, exp.Is):
            if isinstance(node.expression, exp.Null):
                return f"{_convert(node.this)} \\text{{ is null}}"
            return f"{_convert(node.this)} \\text{{ is }} {_convert(node.expression)}"

        # Cast
        if isinstance(node, exp.Cast):
            return _convert(node.this)

        # Arithmetic operations
        if isinstance(node, exp.Div):
            num = _convert(node.this)
            denom = _convert(node.expression)
            return f"\\frac{{{num}}}{{{denom}}}"

        if isinstance(node, exp.Mul):
            left = _convert(node.this)
            right = _convert(node.expression)
            return f"{left} \\cdot {right}"

        if isinstance(node, exp.Add):
            left = _convert(node.this)
            right = _convert(node.expression)
            return f"{left} + {right}"

        if isinstance(node, exp.Sub):
            left = _convert(node.this)
            right = _convert(node.expression)
            return f"{left} - {right}"

        # Coalesce
        if isinstance(node, exp.Coalesce):
            all_nodes = ([node.this] if node.this is not None else []) + list(node.expressions or [])
            args = [_convert(a) for a in all_nodes]
            if len(args) == 2 and args[1] in ("0", "0.0"):
                return f"\\left( {args[0]} \\mid 0 \\right)"
            return f"\\text{{coalesce}}\\left({', '.join(args)}\\right)"

        # Nullif
        if isinstance(node, exp.Nullif):
            return _convert(node.this)

        # Anonymous functions (ClickHouse functions)
        if isinstance(node, exp.Anonymous):
            name = node.this.lower()
            if name == "nullif":
                return _convert(node.expressions[0])
            if name in ("least", "min"):
                return f"\\min\\left({', '.join(_convert(e) for e in node.expressions)}\\right)"
            if name in ("greatest", "max"):
                return f"\\max\\left({', '.join(_convert(e) for e in node.expressions)}\\right)"
            if name == "if" and len(node.expressions) >= 3:
                cond = _convert(node.expressions[0])
                then_val = _convert(node.expressions[1])
                else_val = _convert(node.expressions[2])
                return f"\\begin{{cases}} {then_val} & \\text{{if }} {cond} \\\\ {else_val} & \\text{{otherwise}} \\end{{cases}}"
            if name == "multiif":
                args = list(node.expressions or [])
                lines = []
                i = 0
                while i + 1 < len(args):
                    cond = _convert(args[i])
                    val = _convert(args[i+1])
                    lines.append(f"{val} & \\text{{if }} {cond}")
                    i += 2
                if i < len(args):
                    lines.append(f"{_convert(args[i])} & \\text{{otherwise}}")
                return "\\begin{cases} " + " \\\\ ".join(lines) + " \\end{cases}"
            return f"\\text{{{name}}}\\left({', '.join(_convert(e) for e in node.expressions)}\\right)"

        # Parenthesized / Groupings
        if isinstance(node, exp.Paren):
            return f"\\left( {_convert(node.this)} \\right)"

        # Identifiers / Columns
        if isinstance(node, (exp.Column, exp.Identifier)):
            col_name = node.sql().split(".")[-1].strip("`\"'")
            sym = _clean_symbol(col_name)
            g = _glossary_entry(col_name)
            raw_name = node.sql().split(".")[-1].strip("`\"'")
            raw_name = re.sub(r"/\*.*?\*/", "", raw_name, flags=re.DOTALL).strip()
            sym = _clean_symbol(raw_name)
            g = _glossary_entry(raw_name)
            if g:
                variables[g[0]] = g[1]
            return sym

        # Literals
        if isinstance(node, exp.Literal):
            return str(node.this)
            val = str(node.this)
            if getattr(node, "is_string", False) or (val.startswith("'") and val.endswith("'")):
                clean_val = _escape_latex_text(val.strip("'\""))
                return f"\\text{{'{clean_val}'}}"
            return val
            return _escape_latex_text(val)

        # Fallback to standard SQL text
        return node.sql("clickhouse")
        # Fallback to standard SQL text, safely escaped
        fallback_sql = node.sql("clickhouse")
        fallback_sql = re.sub(r"/\*.*?\*/", "", fallback_sql, flags=re.DOTALL).strip()
        escaped_sql = _escape_latex_text(fallback_sql)
        return f"\\text{{{escaped_sql}}}"

    latex = _convert(parsed)
    return latex, variables
