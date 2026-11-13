"""Phase-2 agent JSON shape: Kind VeraLabV1 = Framework bundle + VeraBase data facet.

Validated for `main.py` via `resolve_sigmarail_lab` → `wire_framework_bundle_v1(..., store=...)` (see `docs/OOD_UNIFIED_FRAMEWORK_PLAN.md`).
This module exists for schema export, validation, and MCP/agent parity with the roadmap.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .lean_framework_json import FrameworkBundleV1
from .data_sources import DataSourceSpec


def _coerce_vera_base_universe(v: Any) -> dict[str, Any]:
    """``universe_query_v1`` / ``v2`` dict only (validated at REST compile time in VeraBase)."""
    if isinstance(v, dict):
        if v.get("version") in (1, 2) and isinstance(v.get("select"), list):
            return v
        raise ValueError(
            "VeraBase.Universe must be universe_query_v1 or v2 (version in (1, 2), select[])"
        )
    raise TypeError(f"Universe must be universe_query_v1/v2 dict, got {type(v)!r}")


VeraBaseUniverse = Annotated[dict[str, Any], BeforeValidator(_coerce_vera_base_universe)]


class EvaluationSettings(BaseModel):
    """Backtest / paper window and account identity. Live uses cash + benchmark; dates are research."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    start_date: str | None = None
    end_date: str | None = None
    initial_cash: float | None = None
    benchmark: str | None = None


class VeraBaseFacet(BaseModel):
    """Data-plane facet (sibling to Framework); universe drives ClickHouse screener when wired."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    universe: VeraBaseUniverse = Field(alias="Universe")
    policy_graph: Optional[dict[str, Any]] = Field(default=None, alias="PolicyGraph")
    pipeline: Optional[dict[str, Any]] = Field(default=None, alias="Pipeline")
    regime: Optional[dict[str, Any]] = Field(default=None, alias="Regime")
    data_sources: list[DataSourceSpec] = Field(default_factory=list, alias="DataSources")
    evaluation: Optional[EvaluationSettings] = Field(default=None, alias="Evaluation")


class VeraLabV1Document(BaseModel):
    """Target Phase-2 document: explicit framework types + VeraBase.Universe (+ plugin parameters)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal[2] = Field(alias="SchemaVersion")
    kind: Literal["VeraLabV1"] = Field(alias="Kind")
    title: str | None = Field(
        default=None,
        description="Human strategy name (compile/decompile round-trip; optional at runtime)",
    )
    framework: FrameworkBundleV1 = Field(alias="Framework")
    algorithm_parameters: dict[str, str] = Field(
        default_factory=dict,
        alias="AlgorithmParameters",
        description="Keys passed via SetParameter (regime-source, exit-mode, …) when composed with CH alpha",
    )
    vera_base: VeraBaseFacet = Field(alias="VeraBase")

    @model_validator(mode="after")
    def _validate_clickhouse_framework(self) -> Self:
        from .sigmarail_lab_v1_ch_parameters import validate_sigmarail_lab_v1_framework_bundle

        validate_sigmarail_lab_v1_framework_bundle(self.framework)
        return self
