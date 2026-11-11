"""Pin the Sharadar-derived RVAB table and transform contract."""

from pathlib import Path

from sigmarail.transform_sql import discover_transform_specs

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "src" / "sigmarail" / "sql" / "schema"


def test_ticker_rvab_schema_and_transform_are_packaged():
    path = SCHEMA_DIR / "144-schema-daily-screener-rvab.sql"
    sql = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS ticker_rvab_daily" in sql
    assert "CREATE VIEW IF NOT EXISTS xform_ticker_rvab_daily" in sql
    for column in ("rvab_score", "atr_stop_baseline", "spy_atr_missing"):
        assert column in sql
    spec = next(s for s in discover_transform_specs() if s.target == "ticker_rvab_daily")
    assert "screener_price_tech_daily" in spec.sources
    assert "screener_factor_daily" in spec.sources
