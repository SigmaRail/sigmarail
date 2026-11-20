"""Reusable setup expression recipes (FilterTree packs) for Studio / compose.

Champion no longer seeds breakout∨VCP∨pocket into ``minervini_sepa`` by default.
These recipes are the maintained catalog: apply via ``apply_setup_recipe`` /
``compose_minervini_sepa_with_setup`` (tests + scripts) or via Studio Measures
(+ Add Filter / expression browser mirrors for leaf recipes).

Keep leaf thresholds in sync with ``VeraScreeningStudio/.../expressionRecipes.ts``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sigmarail.features.strategy.pipeline import (
    PipelineDocument,
    Stage,
    champion_default_bindings,
    champion_default_policy_rules,
)

# --- Leaf / pack trees (SSOT for composed Champion setup) -------------------

VOLUME_THRUST_BREAKOUT: dict[str, Any] = {
    "logic": "and",
    "name": "volume_thrust_breakout",
    "conditions": [
        {"op": "gte", "left": "high", "right": "high_90d", "right_kind": "col"},
        {
            "op": "gte",
            "left": "volume",
            "right": {
                "type": "formula",
                "op": "*",
                "args": [
                    {"type": "col", "name": "avg_vol_50d"},
                    {"type": "lit", "value": 1.40},
                ],
            },
            "right_kind": "formula",
        },
    ],
}

VCP_COMPRESSION: dict[str, Any] = {
    "logic": "and",
    "name": "vcp_compression",
    "conditions": [
        {"op": "lte", "left": "vcp_atr_compression_5d_90d", "right": 0.40},
        {"op": "lte", "left": "vcp_volume_dryup_5d_90d", "right": 0.70},
        {
            "op": "gte",
            "left": "close",
            "right": {
                "type": "formula",
                "op": "*",
                "args": [
                    {"type": "col", "name": "high_90d"},
                    {"type": "lit", "value": 0.90},
                ],
            },
            "right_kind": "formula",
        },
    ],
}

POCKET_PIVOT: dict[str, Any] = {
    "logic": "and",
    "name": "pocket_pivot",
    "conditions": [{"op": "gte", "left": "pocket_pivot_score", "right": 30}],
}

CHAMPION_SETUP_OR: dict[str, Any] = {
    "logic": "or",
    "name": "champion_setup",
    "conditions": [
        deepcopy(VOLUME_THRUST_BREAKOUT),
        deepcopy(VCP_COMPRESSION),
        deepcopy(POCKET_PIVOT),
    ],
}


class SetupRecipe:
    """Named setup pack with instructions for authors and compose helpers."""

    __slots__ = ("id", "label", "desc", "usage", "tree", "purposes")

    def __init__(
        self,
        *,
        id: str,
        label: str,
        desc: str,
        usage: str,
        tree: dict[str, Any],
        purposes: tuple[str, ...] = ("filter", "setup"),
    ) -> None:
        self.id = id
        self.label = label
        self.desc = desc
        self.usage = usage
        self.tree = tree
        self.purposes = purposes

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "desc": self.desc,
            "usage": self.usage,
            "purposes": list(self.purposes),
            "tree": deepcopy(self.tree),
        }


SETUP_RECIPES: dict[str, SetupRecipe] = {
    "volume_thrust_breakout": SetupRecipe(
        id="volume_thrust_breakout",
        label="Volume Thrust Breakout",
        desc="High clears 90d high with volume ≥ 1.4× 50d average.",
        usage=(
            "Add as a setup ALL-group (or OR-sibling) on the setup_pass measure. "
            "Pairs with pivot_breakout entry triggers at runtime."
        ),
        tree=VOLUME_THRUST_BREAKOUT,
    ),
    "vcp_compression": SetupRecipe(
        id="vcp_compression",
        label="VCP Compression",
        desc="ATR/volume dry-up vs 90d + close within 10% of 90d high.",
        usage=(
            "Classic Minervini VCP boolean. Prefer as one OR arm of champion_setup_or, "
            "not as a screens_hit gate."
        ),
        tree=VCP_COMPRESSION,
    ),
    "pocket_pivot": SetupRecipe(
        id="pocket_pivot",
        label="Pocket Pivot",
        desc="L7 pocket_pivot_score ≥ 30.",
        usage="Optional OR arm for institutional volume thrust without a full VCP.",
        tree=POCKET_PIVOT,
    ),
    "champion_setup_or": SetupRecipe(
        id="champion_setup_or",
        label="Champion Setup (breakout ∨ VCP ∨ pocket)",
        desc="Canonical SEPA setup_pass OR-group used by compose tests / scripts.",
        usage=(
            "Apply via compose_minervini_sepa_with_setup() or apply_setup_recipe(..., "
            "'champion_setup_or'). Not seeded on the bare minervini_sepa preset."
        ),
        tree=CHAMPION_SETUP_OR,
    ),
}


def list_setup_recipes() -> list[dict[str, Any]]:
    return [r.as_dict() for r in SETUP_RECIPES.values()]


def get_setup_recipe(recipe_id: str) -> SetupRecipe:
    try:
        return SETUP_RECIPES[recipe_id]
    except KeyError as exc:
        known = ", ".join(sorted(SETUP_RECIPES))
        raise KeyError(f"Unknown setup recipe {recipe_id!r}; known: {known}") from exc


def _set_setup_filters(doc: PipelineDocument, trees: list[dict[str, Any]]) -> PipelineDocument:
    stages = list(doc.stages)
    found = False
    for i, st in enumerate(stages):
        if st.mode == "signal" and (
            (st.id or "") == "setup_pass" or (st.filters and not st.entry_triggers)
        ):
            stages[i] = Stage.model_validate(
                {
                    **st.model_dump(mode="python"),
                    "id": st.id or "setup_pass",
                    "filters": deepcopy(trees),
                }
            )
            found = True
            break
    if not found:
        stages.append(
            Stage.model_validate(
                {
                    "id": "setup_pass",
                    "name": "Setup Group",
                    "mode": "signal",
                    "filters": deepcopy(trees),
                    "max_candidates": 100,
                    "documentation": {
                        "purpose": "Applied from setup_recipes catalog.",
                    },
                }
            )
        )
    return doc.model_copy(update={"stages": stages})


def apply_setup_recipe(
    doc: PipelineDocument,
    recipe_id: str = "champion_setup_or",
    *,
    replace: bool = True,
) -> PipelineDocument:
    """Attach a setup recipe tree onto the setup_pass signal stage."""
    recipe = get_setup_recipe(recipe_id)
    tree = deepcopy(recipe.tree)
    if replace:
        next_doc = _set_setup_filters(doc, [tree])
    else:
        existing: list[dict[str, Any]] = []
        for st in doc.stages:
            if st.mode == "signal" and (st.id or "") == "setup_pass":
                existing = [f.model_dump(mode="python") for f in (st.filters or [])]
                break
        existing.append(tree)
        next_doc = _set_setup_filters(doc, existing)
    # Restore Champion setup binding once a setup column exists.
    bindings = champion_default_bindings(
        min_screens=int(doc.min_screens or 1),
        min_rs_rating=doc.min_rs_rating if doc.min_rs_rating is not None else 85.0,
        rank_by_rs=getattr(doc, "rank_by_rs", True),
        include_setup=True,
    )
    rules = champion_default_policy_rules(
        min_screens=int(doc.min_screens or 1),
        min_rs_rating=doc.min_rs_rating if doc.min_rs_rating is not None else 85.0,
        rank_by_rs=getattr(doc, "rank_by_rs", True),
        include_setup=True,
    )
    # Keep any extra policy rules (eps_beat, etc.) beyond the champion defaults.
    base_ids = {r.id for r in rules}
    extras = [r for r in (doc.policy_rules or []) if r.id not in base_ids]
    return next_doc.model_copy(
        update={
            "bindings": bindings,
            "policy_rules": list(rules) + extras,
        }
    )


def compose_minervini_sepa_with_setup(
    *,
    preset_id: str = "minervini_sepa",
    setup_recipe_id: str = "champion_setup_or",
) -> PipelineDocument:
    """Maintained Champion compose: bare preset + optional setup recipe pack.

    Use this in unit tests / scripts instead of baking setup AST into the preset.
    """
    from sigmarail.features.strategy.presets import get_preset

    base = get_preset(preset_id)
    return apply_setup_recipe(base, setup_recipe_id, replace=True)
