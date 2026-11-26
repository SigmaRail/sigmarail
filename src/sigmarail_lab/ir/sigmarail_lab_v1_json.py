"""Phase-2 agent JSON shape: Kind SigmaRailStrategyV1 = Framework bundle + SigmaRail data facet.

Validated for `main.py` via `resolve_sigmarail_lab` → `wire_framework_bundle_v1(..., store=...)` (see `docs/OOD_UNIFIED_FRAMEWORK_PLAN.md`).
This module exists for schema export, validation, and MCP/agent parity with the roadmap.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .lean_framework_json import SigmaRailStrategyFrameworkV1
from .data_sources import DataSourceSpec


class EvaluationSettings(BaseModel):
    """Backtest / paper window and account identity. Live uses cash + benchmark; dates are research."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    start_date: str | None = None
    end_date: str | None = None
    initial_cash: float | None = None
    benchmark: str | None = None


class SigmaRailFacet(BaseModel):
    """Data-plane settings; universe configuration lives in Framework.UniverseSelection."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    policy_graph: Optional[dict[str, Any]] = Field(default=None, alias="PolicyGraph")
    pipeline: Optional[dict[str, Any]] = Field(default=None, alias="Pipeline")
    regime: Optional[dict[str, Any]] = Field(default=None, alias="Regime")
    data_sources: list[DataSourceSpec] = Field(default_factory=list, alias="DataSources")
    evaluation: Optional[EvaluationSettings] = Field(default=None, alias="Evaluation")


class SigmaRailStrategyV1Document(BaseModel):
    """Current strategy document with five fixed SigmaRail framework slots."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal[3] = Field(alias="SchemaVersion")
    kind: Literal["SigmaRailStrategyV1"] = Field(alias="Kind")
    title: str | None = Field(
        default=None,
        description="Human strategy name (compile/decompile round-trip; optional at runtime)",
    )
    framework: SigmaRailStrategyFrameworkV1 = Field(alias="Framework")
    algorithm_parameters: dict[str, str] = Field(
        default_factory=dict,
        alias="AlgorithmParameters",
        description="Keys passed via SetParameter (regime-source, exit-mode, …) when composed with CH alpha",
    )
    sigmarail_base: SigmaRailFacet = Field(alias="SigmaRail")
