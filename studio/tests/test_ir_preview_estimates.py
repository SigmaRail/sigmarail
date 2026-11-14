"""Street consensus fields belong in the Studio field catalog (not house fwd_eps)."""

from __future__ import annotations

from screens.ir_preview import (
    _PRIORITY_FIELDS,
    _categorize_field,
    _CATEGORY_LABELS,
    _FIELD_DESCRIPTIONS,
)


def test_priority_includes_street_consensus_not_only_house_forecast() -> None:
    for col in (
        "eps_cq_mean",
        "eps_ny_mean",
        "eps_ny_rev_pct_90d",
        "eps_nq_rev_pct_90d",
        "eps_last_surprise_pct",
        "sma200_lag_30d",
    ):
        assert col in _PRIORITY_FIELDS
    assert "fwd_eps_1y" in _PRIORITY_FIELDS


def test_stage_catalog_uses_detailed_neutral_fields() -> None:
    assert "stage_code" in _PRIORITY_FIELDS
    assert "stage_duration" in _PRIORITY_FIELDS
    assert "stage_primary" not in _PRIORITY_FIELDS
    assert "stage_code" in _FIELD_DESCRIPTIONS
    assert "stage_duration" in _FIELD_DESCRIPTIONS


def test_consensus_fields_are_estimates_category() -> None:
    assert _categorize_field("eps_ny_rev_pct_90d") == "estimates"
    assert _categorize_field("eps_last_surprise_pct") == "estimates"
    assert _categorize_field("eps_cq_mean") == "estimates"
    assert _categorize_field("fwd_eps_1y") == "forecast"
    assert _CATEGORY_LABELS["estimates"] == "Estimates (street consensus)"
    assert "eps_ny_rev_pct_90d" in _FIELD_DESCRIPTIONS


def test_estimate_human_labels() -> None:
    from screens.ir_preview import _humanize_label

    assert _humanize_label("eps_cq_mean") == "EPS CQ Mean (street)"
    assert _humanize_label("eps_ny_rev_pct_90d") == "NY EPS 90d revision %"
    assert _humanize_label("eps_beat_flag") == "Last EPS Beat Flag"
    assert _humanize_label("sales_beat_flag") == "Last Sales Beat Flag"
    assert _humanize_label("sales_last_surprise_pct") == "Last Sales Surprise %"


def test_new_estimate_fields_in_catalog() -> None:
    from screens.ir_preview import _FIELD_DESCRIPTIONS, _PRIORITY_FIELDS

    for field in (
        "eps_last_reported",
        "eps_last_estimate",
        "eps_beat_flag",
        "sales_last_reported",
        "sales_last_estimate",
        "sales_last_surprise_pct",
        "sales_beat_flag",
    ):
        assert field in _PRIORITY_FIELDS
        assert field in _FIELD_DESCRIPTIONS
        assert _categorize_field(field) == "estimates"
