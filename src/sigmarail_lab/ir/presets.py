"""Named criteria bundles for graph filter steps (no SQL in JSON)."""

from __future__ import annotations

from sigmarail_spec import AllExpr, AnyExpr, BoolExprItem, ColEqExpr, ColGteExpr, InTickersExpr
from .screener_columns import ScreenerColumn

_PRESETS: dict[str, AnyExpr] = {}


def _register_minervini_v1() -> None:
    # Match legacy UniverseSpec OR: always-include SPY OR full Minervini gate (see query_compile).
    _PRESETS["minervini_v1"] = AnyExpr(
        items=[
            InTickersExpr(type="in_tickers", tickers=["SPY"]),
            AllExpr(
                items=[
                    ColGteExpr(column=ScreenerColumn.CLOSE, value=5.0),
                    ColGteExpr(column=ScreenerColumn.VOLUME, value=2_000_000),
                    ColEqExpr(column=ScreenerColumn.HAS_VCP_SETUP, value=True),
                    ColEqExpr(column=ScreenerColumn.IS_STAGE_2_ADVANCING, value=True),
                    ColGteExpr(column=ScreenerColumn.MINERVINI_TT_SCORE_FULL, value=6.0),
                ]
            ),
        ]
    )


_register_minervini_v1()


def get_preset_criteria(preset_id: str) -> BoolExprItem:
    key = (preset_id or "").strip()
    if not key:
        raise ValueError("preset id is empty")
    bundle = _PRESETS.get(key)
    if bundle is None:
        raise ValueError(f"unknown filter preset: {key!r}")
    return bundle


def list_preset_ids() -> tuple[str, ...]:
    return tuple(sorted(_PRESETS.keys()))
