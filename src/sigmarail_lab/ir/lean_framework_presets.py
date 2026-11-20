"""Named Framework bundles for LeanFrameworkV1 (JSON FrameworkPreset)."""

from __future__ import annotations

import copy
from typing import Any

# Mirrors tests/fixtures/ir/lean_framework_v1_minimal.json "Framework".
_MINIMAL_RSI_SPY_QQQ: dict[str, Any] = {
    "UniverseSelection": {
        "Type": "ManualUniverseSelectionModel",
        "Parameters": {
            "symbols": ["SPY", "QQQ"],
        },
    },
    "Alpha": {
        "Type": "RsiAlphaModel",
        "Parameters": {
            "period": 14,
            "resolution": "Daily",
        },
    },
    "PortfolioConstruction": {
        "Type": "EqualWeightingPortfolioConstructionModel",
        "Parameters": {},
    },
    "Execution": {
        "Type": "ImmediateExecutionModel",
        "Parameters": {},
    },
    "RiskManagement": {
        "Type": "MaximumDrawdownPercentPerSecurity",
        "Parameters": {
            "maximum_drawdown_percent": 0.1,
        },
    },
}

LEAN_FRAMEWORK_PRESETS: dict[str, dict[str, Any]] = {
    "minimal_rsi_spy_qqq": _MINIMAL_RSI_SPY_QQQ,
}


def list_lean_framework_preset_ids() -> tuple[str, ...]:
    return tuple(sorted(LEAN_FRAMEWORK_PRESETS.keys()))


def get_lean_framework_preset_bundle(preset_id: str) -> dict[str, Any]:
    key = (preset_id or "").strip()
    if not key:
        raise ValueError("FrameworkPreset must be a non-empty string")
    if key not in LEAN_FRAMEWORK_PRESETS:
        raise ValueError(f"unknown LeanFrameworkV1 FrameworkPreset: {key!r}")
    return copy.deepcopy(LEAN_FRAMEWORK_PRESETS[key])
