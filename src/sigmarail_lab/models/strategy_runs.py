"""Pydantic model for strategy backtest run persistence (ClickHouse strategy_runs table)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


RunType = Literal["base", "optimization", "variant", "stress_test", "spike_hosted"]
MarketRegime = Literal["bull", "bear", "neutral"]
ArtifactType = Literal[
    "summary",
    "backtest_results",
    "order_events",
    "algorithm_log",
    "live_snapshot",
    "backtest_day_snapshots",
    "accounting_ledger",
]


def _clean_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _parse_float_rate(v: Any) -> Optional[float]:
    """Parse percentage string (e.g. '4.415%', '63%') or number into a unit fraction (0.04415, 0.63)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float, Decimal)):
        val = float(v)
    else:
        s = str(v).strip().replace(",", "")
        if s.endswith("%"):
            return float(s[:-1].strip()) / 100.0
        try:
            val = float(s)
        except ValueError:
            return None

    # Canonical rule: rates in strategy_runs are unit fractions (e.g. 0.0441 = +4.41%, 0.63 = 63% win rate).
    # If a non-fractional percentage number like 4.415 or 63.0 is provided, normalize it.
    if abs(val) > 1.0:
        return val / 100.0
    return val


def _parse_currency_float(v: Any) -> Optional[float]:
    """Parse dollar amount (e.g. '$104,415.00', '-$387.64') into float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_uint(v: Any) -> Optional[int]:
    """Parse integer count (e.g. '344', 344)."""
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).strip().replace(",", "")))
    except (ValueError, TypeError):
        return None


def closed_trade_metrics(artifact: Any) -> dict[str, Any]:
    """Derive gross metrics only from complete LEAN totalPerformance evidence.

    profitLoss is gross realized P&L; fees are reported separately, never deducted.
    No raw evidence or evidence-controlled text is returned.
    """
    import math

    result = {"profit_factor": None, "status": "unavailable",
              "source": "unavailable", "closed_record_win_rate": None,
              "closed_record_count": None, "gross_profit": None, "gross_loss": None,
              "pnl_basis": "gross_before_fees"}

    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError
        value = float(value)
        if not math.isfinite(value):
            raise ValueError
        return value

    try:
        performance = artifact["totalPerformance"]
        stats = performance["tradeStatistics"]
        count = number(stats["totalNumberOfTrades"])
        if count <= 0 or not count.is_integer():
            return result
        trades = performance.get("closedTrades")
        if "closedTrades" in performance:
            if not isinstance(trades, list) or len(trades) != count:
                return result
            outcomes = [number(trade["profitLoss"]) for trade in trades]
            profit = math.fsum(v for v in outcomes if v > 0)
            loss = -math.fsum(v for v in outcomes if v < 0)
            result["closed_record_win_rate"] = sum(v > 0 for v in outcomes) / count
            source = "totalPerformance.closedTrades"
        else:
            profit = number(stats["totalProfit"])
            loss = -number(stats["totalLoss"])
            source = "totalPerformance.tradeStatistics"
        if profit < 0 or loss < 0:
            return result
        result.update(source=source, closed_record_count=int(count),
                      gross_profit=profit, gross_loss=loss)
        if profit == loss == 0:
            return result
        if loss == 0:
            result["status"] = "infinite"
        else:
            ratio = profit / loss
            if math.isfinite(ratio):
                result.update(profit_factor=ratio, status="available")
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return result


class StrategyRunRecord(BaseModel):
    """Validated strategy run record matching ClickHouse `strategy_runs` schema.

    All rate and return metrics (total_return, annual_return, max_drawdown, win_rate, spy_return)
    are strictly stored as unit fractions (e.g., 0.04415 for +4.415%, 0.63 for 63% win rate).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # Identity & Provenance
    run_id: str
    strategy_id: str
    strategy_repo_url: str = "local"
    run_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )
    git_commit: str = "local"
    git_branch: str = "local"
    run_type: RunType = "base"
    trigger: str = "manual"
    period_start: str
    period_end: str
    image: str = ""
    parameters: str = "{}"
    ir_id: Optional[str] = None
    ir_schema_version: Optional[int] = None
    ir_content_hash: Optional[str] = None

    # Performance Metrics (stored as unit fractions or floats)
    total_return: Optional[float] = None
    annual_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_orders: Optional[int] = None
    total_fees: Optional[float] = None
    start_equity: Optional[float] = None
    end_equity: Optional[float] = None

    # Risk & Benchmark
    alpha: Optional[float] = None
    beta: Optional[float] = None
    volatility: Optional[float] = None
    information_ratio: Optional[float] = None
    market_regime: Optional[MarketRegime] = None
    spy_return: Optional[float] = None

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def validate_date_str(cls, v: Any) -> str:
        if isinstance(v, (date, datetime)):
            return v.strftime("%Y-%m-%d")
        s = _clean_str(v)
        if not s:
            raise ValueError("Period date cannot be empty")
        # Validate format YYYY-MM-DD
        date.fromisoformat(s[:10])
        return s[:10]

    @field_validator("total_return", "annual_return", "max_drawdown", "win_rate", "spy_return", mode="before")
    @classmethod
    def validate_rate(cls, v: Any) -> Optional[float]:
        return _parse_float_rate(v)

    @field_validator("start_equity", "end_equity", "total_fees", mode="before")
    @classmethod
    def validate_currency(cls, v: Any) -> Optional[float]:
        return _parse_currency_float(v)

    @field_validator("sharpe_ratio", "sortino_ratio", "profit_factor", "alpha", "beta", "volatility", "information_ratio", mode="before")
    @classmethod
    def validate_float_metric(cls, v: Any) -> Optional[float]:
        return _parse_currency_float(v)

    @field_validator("total_orders", mode="before")
    @classmethod
    def validate_orders(cls, v: Any) -> Optional[int]:
        return _parse_uint(v)

    @classmethod
    def from_lean_summary(
        cls,
        summary: dict[str, Any],
        *,
        run_id: str,
        strategy_id: str,
        backtest_results: Any = None,
        period_start: str | date,
        period_end: str | date,
        run_type: RunType = "base",
        strategy_repo_url: str = "local",
        git_commit: str = "local",
        git_branch: str = "local",
        trigger: str = "manual",
        image: str = "",
        parameters: str = "{}",
        ir_id: Optional[str] = None,
        ir_schema_version: Optional[int] = None,
        ir_content_hash: Optional[str] = None,
    ) -> StrategyRunRecord:
        """Create a StrategyRunRecord from a raw LEAN summary dictionary (with 'statistics' key)."""
        stats = summary.get("statistics") or {}
        runtime_stats = summary.get("runtimeStatistics") or {}

        derived = closed_trade_metrics(backtest_results if backtest_results is not None else summary)
        # Preserve legacy opaque parameter payloads; current producers use objects.
        try:
            parameter_data = json.loads(parameters)
        except (ValueError, TypeError, RecursionError):
            parameter_data = None
        if isinstance(parameter_data, dict):
            parameter_data["_metric_metadata"] = {"profit_factor": derived}
            parameters = json.dumps(parameter_data, separators=(",", ":"))

        return cls(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_repo_url=strategy_repo_url,
            git_commit=git_commit,
            git_branch=git_branch,
            run_type=run_type,
            trigger=trigger,
            period_start=period_start if isinstance(period_start, str) else period_start.strftime("%Y-%m-%d"),
            period_end=period_end if isinstance(period_end, str) else period_end.strftime("%Y-%m-%d"),
            image=image,
            parameters=parameters,
            ir_id=ir_id,
            ir_schema_version=ir_schema_version,
            ir_content_hash=ir_content_hash,
            total_return=stats.get("Total Return") or stats.get("Net Profit") or runtime_stats.get("Return"),
            annual_return=stats.get("Compounding Annual Return"),
            sharpe_ratio=stats.get("Sharpe Ratio"),
            sortino_ratio=stats.get("Sortino Ratio"),
            max_drawdown=stats.get("Drawdown"),
            win_rate=stats.get("Win Rate"),
            profit_factor=derived["profit_factor"],
            total_orders=stats.get("Total Orders"),
            total_fees=stats.get("Total Fees") or runtime_stats.get("Fees"),
            start_equity=stats.get("Starting Capital") or stats.get("Start Equity"),
            end_equity=stats.get("Ending Capital") or stats.get("End Equity") or runtime_stats.get("Equity"),
            alpha=stats.get("Alpha"),
            beta=stats.get("Beta"),
            volatility=stats.get("Annual Standard Deviation"),
            information_ratio=stats.get("Information Ratio"),
        )

    def to_clickhouse_row(self) -> dict[str, Any]:
        """Serialize into ClickHouse JSONEachRow payload dict."""
        return self.model_dump(exclude_none=True)


class ArtifactRecord(BaseModel):
    """Validated artifact payload matching ClickHouse `strategy_run_artifacts` schema."""

    run_id: str
    strategy_id: str
    run_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )
    artifact_type: ArtifactType
    artifact_json: str

    @field_validator("artifact_json", mode="before")
    @classmethod
    def validate_json_payload(cls, v: Any) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, separators=(",", ":"))
        s = _clean_str(v)
        if not s:
            raise ValueError("Artifact payload cannot be empty")
        # Validate that it is valid JSON
        json.loads(s)
        return s

    def to_clickhouse_row(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)
