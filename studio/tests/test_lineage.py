"""Tests for lineage helpers."""

from __future__ import annotations

from screens.lineage import (
    build_lineage_parameters,
    merge_lineage_into_compose,
    universe_spec_hash,
)


def test_universe_spec_hash_stable() -> None:
    spec = {"version": 1, "from": "daily_screener", "select": ["ticker"], "where": {"type": "all", "items": []}}
    h1 = universe_spec_hash(spec)
    h2 = universe_spec_hash(dict(spec))
    assert h1 == h2
    assert len(h1) == 64


def test_build_lineage_parameters() -> None:
    spec = {"version": 1, "from": "daily_screener", "select": ["ticker"], "where": {"type": "all", "items": []}}
    out = build_lineage_parameters(spec, screen_id=3, screen_name="Leaders")
    assert out["studio_screen_id"] == "3"
    assert out["studio_screen_name"] == "Leaders"
    assert out["studio_spec_hash"] == universe_spec_hash(spec)


def test_merge_lineage_into_compose() -> None:
    merged = merge_lineage_into_compose({"regime-source": "ch"}, {"studio_spec_hash": "abc"})
    assert merged["regime-source"] == "ch"
    assert merged["studio_spec_hash"] == "abc"
