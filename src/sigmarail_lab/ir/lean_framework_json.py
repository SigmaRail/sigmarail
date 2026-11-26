"""Agent-facing Lean framework JSON (Phase 1): Kind LeanFrameworkV1.

PascalCase JSON keys via Pydantic aliases; no dependency on pipeline SigmaRailLab or ClickHouse.
See docs/LEAN_FRAMEWORK_V1.md and the OOD Pydantic plan.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrameworkSlotSpec(BaseModel):
    """One framework slot: QC class name + constructor kwargs."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: str = Field(alias="Type", description="Allowlisted Lean / QC Python class name")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")

    @model_validator(mode="after")
    def _parameters_match_allowlisted_type(self) -> Self:
        from .lean_framework_parameters import validate_slot_parameters_for_type

        validate_slot_parameters_for_type(self.type, self.parameters)
        return self


class FrameworkBundleV1(BaseModel):
    """Four LEAN model slots for a standalone LeanFrameworkV1 document."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    alpha: FrameworkSlotSpec = Field(alias="Alpha")
    portfolio_construction: FrameworkSlotSpec = Field(alias="PortfolioConstruction")
    execution: FrameworkSlotSpec = Field(alias="Execution")
    risk_management: FrameworkSlotSpec = Field(alias="RiskManagement")


class FixedClickHouseUniverseSelectionV1(BaseModel):
    """Fixed ClickHouse query universe; the AST is this slot's configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["SigmaRailClickHouseUniverseSelection"] = Field(alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")

    @model_validator(mode="after")
    def _query_is_present(self) -> Self:
        query = self.parameters.get("query")
        if not isinstance(query, dict) or query.get("version") not in (1, 2) or not isinstance(query.get("select"), list):
            raise ValueError("UniverseSelection.Parameters.query must be a universe_query_v1/v2 AST")
        if set(self.parameters) != {"query"}:
            raise ValueError("UniverseSelection.Parameters accepts only the query AST")
        return self

class FixedSigmaRailAlphaV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    type: Literal["SigmaRailScreenerAlphaModel"] = Field(alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")


class FixedSigmaRailPortfolioConstructionV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    type: Literal["SigmaRailScreenerPortfolioConstructionModel"] = Field(alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")

class FixedSigmaRailRiskManagementV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    type: Literal["SigmaRailRiskManagementModel"] = Field(alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")

class FixedSigmaRailExecutionV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    type: Literal["SigmaRailScreenerExecutionModel"] = Field(alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")


class SigmaRailStrategyFrameworkV1(BaseModel):
    """Five fixed SigmaRail implementations; Parameters hold all slot configuration."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    universe_selection: FixedClickHouseUniverseSelectionV1 = Field(alias="UniverseSelection")
    alpha: FixedSigmaRailAlphaV1 = Field(alias="Alpha")
    portfolio_construction: FixedSigmaRailPortfolioConstructionV1 = Field(alias="PortfolioConstruction")
    execution: FixedSigmaRailExecutionV1 = Field(alias="Execution")
    risk_management: FixedSigmaRailRiskManagementV1 = Field(alias="RiskManagement")


class LeanFrameworkV1Document(BaseModel):
    """
    Phase-1 document: wire standard QC framework models only (no SigmaRail / ClickHouse).

    JSON uses SchemaVersion + Kind; distinct from legacy pipeline JSON (schema_version: 1).
    Supply **Framework** inline or **FrameworkPreset** (named bundle), not both.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal[2] = Field(alias="SchemaVersion")
    kind: Literal["LeanFrameworkV1"] = Field(alias="Kind")
    algorithm: dict[str, Any] | None = Field(
        default=None,
        alias="Algorithm",
        description="Optional hints (e.g. StartCash); dates/cash v1 from config.json / parameters",
    )
    framework_preset: str | None = Field(
        default=None,
        alias="FrameworkPreset",
        description="Named allowlisted bundle; alternative to inline Framework.",
    )
    framework: FrameworkBundleV1 = Field(alias="Framework")

    @model_validator(mode="before")
    @classmethod
    def _expand_framework_preset(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        preset_raw = data.get("FrameworkPreset")
        has_preset = (
            preset_raw is not None
            and isinstance(preset_raw, str)
            and preset_raw.strip() != ""
        )
        has_framework = data.get("Framework") is not None
        if has_preset and has_framework:
            raise ValueError(
                "LeanFrameworkV1: provide only one of Framework or FrameworkPreset, not both"
            )
        if has_preset:
            from .lean_framework_presets import get_lean_framework_preset_bundle

            data["Framework"] = get_lean_framework_preset_bundle(preset_raw)
        elif not has_framework:
            raise ValueError("LeanFrameworkV1 requires Framework or FrameworkPreset")
        return data
