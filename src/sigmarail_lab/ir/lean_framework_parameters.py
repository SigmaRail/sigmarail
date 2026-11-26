"""Compatibility re-exports for the SigmaRail Spec LEAN parameter contract.

Parameter definitions are owned by ``sigmarail_spec`` so the authoring compiler
and LEAN runtime validate framework models against the same schemas.
"""

from sigmarail_spec.lean_framework_parameters import (
    ConstantAlphaModelParams,
    EqualWeightingPortfolioConstructionModelParams,
    ImmediateExecutionModelParams,
    MaximumDrawdownPercentPerSecurityParams,
    NullRiskManagementModelParams,
    RsiAlphaModelParams,
    SigmaRailCompositeAlphaModelParams,
    SigmaRailHedgeModelParams,
    SigmaRailPyramidAlphaModelParams,
    SigmaRailScreenerExecutionModelParams,
    lean_framework_v1_pydantic_type_ids,
    validate_slot_parameters_for_type,
)

__all__ = [
    "ConstantAlphaModelParams",
    "EqualWeightingPortfolioConstructionModelParams",
    "ImmediateExecutionModelParams",
    "MaximumDrawdownPercentPerSecurityParams",
    "NullRiskManagementModelParams",
    "RsiAlphaModelParams",
    "SigmaRailCompositeAlphaModelParams",
    "SigmaRailHedgeModelParams",
    "SigmaRailPyramidAlphaModelParams",
    "SigmaRailScreenerExecutionModelParams",
    "lean_framework_v1_pydantic_type_ids",
    "validate_slot_parameters_for_type",
]
