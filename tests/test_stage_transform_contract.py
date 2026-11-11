"""Stage compatibility surfaces must project the canonical detailed series."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "sigmarail"


def test_daily_transform_has_no_parallel_broad_classifier():
    sql = (ROOT / "sql/schema/03-schema-daily_metrics_derived.sql").read_text()
    assert "stage_code" in sql and "stage_duration" in sql
    for obsolete_cte in ("stage_decisive AS", "stage_held AS", "stage_labeled AS", "stage_seed AS"):
        assert obsolete_cte not in sql
    assert "w_stage" not in sql


def test_weekly_transform_has_no_parallel_broad_classifier():
    sql = (ROOT / "sql/schema/05-schema-weekly-metrics-derived.sql").read_text()
    assert "stage_code" in sql and "stage_duration" in sql
    assert "w_stage" not in sql
    assert "stage_hist_duration AS" not in sql


def test_daily_screener_projects_only_neutral_canonical_stage_fields():
    sql = (ROOT / "sql/schema/176-schema-screener_price_tech_daily.sql").read_text()
    assert "dmd.stage_code AS `stage_code`" in sql
    assert "dmd.stage_duration AS `stage_duration`" in sql
    assert "w_stage" not in sql


def test_daily_consumers_use_completed_week_availability_cutoff():
    """Monday-labeled weekly bars become visible no earlier than Friday."""
    paths = ("sql/schema/83-schema-stage_analysis.sql",)
    for path in paths:
        sql = (ROOT / path).read_text()
        assert "date + toIntervalDay(4) AS available_date" in sql
        assert ".date >= " in sql and ".available_date" in sql


def test_current_stage_tables_declare_canonical_columns_without_legacy_stage_field():
    for path in (
        "sql/schema/03-schema-daily_metrics_derived.sql",
        "sql/schema/05-schema-weekly-metrics-derived.sql",
    ):
        sql = (ROOT / path).read_text()
        assert "`stage_code`" in sql
        assert "`stage_duration`" in sql
        assert "`w_stage`" not in sql
