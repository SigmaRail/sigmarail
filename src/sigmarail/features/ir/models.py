from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sigmarail_spec import BoolExprItem, validate_bool_expr_depth
from .screener_columns import ScreenerColumn


class UniverseSpec(BaseModel):
    """Logical screener universe: legacy flat fields and/or explicit criteria AST.

    ``source`` is a logical id; compiled SQL joins L7 ``screener_*`` tables
    (never the ``daily_screener`` view). ``screener`` is the canonical id;
    ``daily_screener`` is retained as a deprecated alias.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["screener", "daily_screener"] = "screener"
    criteria: BoolExprItem | None = None
    projection: list[ScreenerColumn] | None = Field(
        default=None,
        description=(
            "daily_screener SELECT columns. If omitted, default is ticker + overall_score + "
            "atr_14_pct only (no OHLC in the result set). Filters may still use close/volume. "
            "Set explicitly to pull extra columns (e.g. close, sma200d) for custom logic."
        ),
    )

    min_close: float | None = Field(default=None, ge=0)
    min_volume: int | None = Field(default=None, ge=0)
    require_has_vcp_setup: bool = True
    require_is_stage_2_advancing: bool = True
    min_minervini_tt_score_full: float | None = None
    limit_per_day: int | None = Field(default=None, ge=1, le=500)
    always_include_tickers: list[str] = Field(
        default_factory=lambda: ["SPY"],
        description="Always include these tickers (e.g. SPY for benchmark/regime).",
    )
    sort_field: ScreenerColumn = Field(default="overall_score")
    sort_direction: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def _universe_shape(self) -> UniverseSpec:
        if self.criteria is not None:
            validate_bool_expr_depth(self.criteria)
            if self.limit_per_day is None:
                raise ValueError("limit_per_day is required when criteria is set")
            return self
        missing: list[str] = []
        if self.min_close is None:
            missing.append("min_close")
        if self.min_volume is None:
            missing.append("min_volume")
        if self.min_minervini_tt_score_full is None:
            missing.append("min_minervini_tt_score_full")
        if self.limit_per_day is None:
            missing.append("limit_per_day")
        if missing:
            raise ValueError(f"legacy universe requires {missing} when criteria is omitted")
        return self

    def to_screener_range_sql(self, start_date_iso: str, end_date_iso: str) -> str:
        """Bulk backtest load SQL for daily_screener (LIMIT n BY date)."""
        from .query_compile import compile_screener_range_query

        return compile_screener_range_query(self, start_date_iso, end_date_iso)

    def to_screener_single_day_sql(self, today_iso: str) -> str:
        """Single-calendar-day universe SQL for live reload."""
        from .query_compile import compile_screener_single_day_query

        return compile_screener_single_day_query(self, today_iso)

    def to_screener_single_day_query(self) -> tuple[str, dict[str, object]]:
        """Parameterized single-day query (no inline literals, no FORMAT)."""
        from .query_compile import compile_screener_single_day_query_param

        return compile_screener_single_day_query_param(self)

    def to_screener_range_query(self) -> tuple[str, dict[str, object]]:
        """Parameterized range query (no inline literals, no FORMAT)."""
        from .query_compile import compile_screener_range_query_param

        return compile_screener_range_query_param(self)

    def model_dump_for_json(self) -> dict[str, Any]:
        """Stable helper for transport; do not include Pydantic internals."""
        return cast(dict[str, Any], self.model_dump())
