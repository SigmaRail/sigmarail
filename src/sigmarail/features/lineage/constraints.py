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


def extract_expression_caveats(
    expr_sql: str,
    *,
    column_name: str = "",
    full_query_sql: str = "",
    ast_expr: Any = None,
) -> list[dict[str, Any]]:
    """Detect limitation classes and mathematical edge cases from a column's expression and transform context."""
    caveats: list[dict[str, Any]] = []
    text_lower = expr_sql.lower()
    full_lower = full_query_sql.lower()

    if _HAS_SQLGLOT and ast_expr is None:
        try:
            ast_expr = sqlglot.parse_one(expr_sql, read="clickhouse")
        except Exception:
            ast_expr = None

    # 1. UNIVERSE_RESTRICTION (Exclusions / Pruning)
    if "broad_market_constituents" in full_lower or "bmc" in full_lower:
        caveats.append(
            {
                "code": "UNIVERSE_RESTRICTION",
                "severity": "info",
                "title": "Universe Filtered to Liquid Peers",
                "description": "Conditioned on broad_market_constituents; OTC, penny, and unlisted securities are excluded upstream.",
            }
        )

    # 2. LOOKBACK_MINIMUM (Required historical bar depth)
    lookback_days = 0
    if "perf_1y" in text_lower or "yearly_performance" in text_lower or "yearly_pct" in text_lower:
        lookback_days = max(lookback_days, 252)
    elif "perf_6m" in text_lower or "performance_6m" in text_lower:
        lookback_days = max(lookback_days, 126)
    elif "perf_3m" in text_lower or "performance_3m" in text_lower:
        lookback_days = max(lookback_days, 63)
    elif "perf_1m" in text_lower or "performance_1m" in text_lower:
        lookback_days = max(lookback_days, 21)

    # Check for window ROWS BETWEEN N PRECEDING
    m_win = re.search(r"between\s+(\d+)\s+preceding", text_lower)
    if m_win:
        lookback_days = max(lookback_days, int(m_win.group(1)) + 1)

    m_sma = re.search(r"sma(\d+)d", column_name.lower())
    if m_sma:
        lookback_days = max(lookback_days, int(m_sma.group(1)))

    if lookback_days > 0:
        caveats.append(
            {
                "code": "LOOKBACK_MINIMUM",
                "severity": "warning",
                "title": f"Requires {lookback_days} Trading Days History",
                "lookback_bars": lookback_days,
                "description": f"Requires at least {lookback_days} trading bars of historical data. Newer listings will return NULL or incomplete scores.",
            }
        )

    # 3. MISSING_DATA_PENALTY (Asymmetric IPO penalty)
    # Pattern: coalesce(col, 0.0) * weight in numerator with unconditioned denominator
    if (
        "coalesce" in text_lower
        and ("0.0" in text_lower or "0" in text_lower)
        and ("yearly" in text_lower or "perf" in text_lower)
        and ("*" in text_lower or "+" in text_lower)
    ):
        caveats.append(
            {
                "code": "MISSING_DATA_PENALTY",
                "severity": "warning",
                "title": "Penalizes Young Listings (IPO Penalty)",
                "description": "Securities lacking full 1-year history default missing horizons to the 0th percentile, mathematically capping their score.",
            }
        )

    # 4. ARBITRARY_TIE_BREAK
    if "row_number()" in text_lower:
        caveats.append(
            {
                "code": "ARBITRARY_TIE_BREAK",
                "severity": "low",
                "title": "Arbitrary Tie-Breaking",
                "description": "Uses row_number() which arbitrarily breaks identical performance ties by physical table scan order.",
            }
        )

    # 5. CROSS_SECTIONAL
    if "partition by date" in text_lower:
        caveats.append(
            {
                "code": "CROSS_SECTIONAL",
                "severity": "info",
                "title": "Cross-Sectional Relative Metric",
                "description": "Ranked across the daily market cohort on date t. A stock's rating reflects its relative performance vs peers, not absolute price change.",
            }
        )

    # 6. DIVIDEND_EXCLUDED
    if "close" in text_lower and "dividend" not in text_lower:
        caveats.append(
            {
                "code": "DIVIDEND_EXCLUDED",
                "severity": "info",
                "title": "Capital Gains Only (Ex-Dividend)",
                "description": "Derived from split-adjusted closing prices; cash dividend distributions and yield are excluded.",
            }
        )

    # 7. NEGATIVE_DIVISOR_EXCLUSION
    if "nullif" in text_lower or ("if(" in text_lower and ("null" in text_lower or "<=" in text_lower or "> 0" in text_lower)):
        caveats.append(
            {
                "code": "NEGATIVE_DIVISOR_EXCLUSION",
                "severity": "warning",
                "title": "Unprofitable / Zero Divisor Exclusion",
                "description": "Returns NULL or drops records when denominator is zero or negative (e.g. unprofitable companies).",
            }
        )

    # 8. WINSORIZATION_CLAMPING
    if "greatest" in text_lower and "least" in text_lower:
        caveats.append(
            {
                "code": "WINSORIZATION_CLAMPING",
                "severity": "info",
                "title": "Outlier Clamped (Winsorized)",
                "description": "Values are bounded between fixed lower and upper bounds to eliminate statistical outlier distortion.",
            }
        )

    # Deduplicate caveats by code
    seen: set[str] = set()
    unique_caveats: list[dict[str, Any]] = []
    for c in caveats:
        if c["code"] not in seen:
            seen.add(c["code"])
            unique_caveats.append(c)

    return unique_caveats
