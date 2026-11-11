"""Acceleration flags are NULL when the QoQ window is incomplete."""

from __future__ import annotations

from pathlib import Path

SQL_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "sigmarail" / "sql"
    / "schema"
    / "167-schema-arq_derived.sql"
)


def test_arq_derived_acceleration_null_when_window_incomplete() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    assert "THEN NULL" in sql
    assert "COUNT(c.eps_growth_qoq_calc) OVER w_qoq_accel < 2" in sql
    assert "COUNT(c.revenue_growth_qoq_calc) OVER w_qoq_accel < 2" in sql
    # Incomplete history must not collapse to 0 (looks like "not accelerating").
    assert "THEN 1 ELSE 0 END as eps_acceleration_qoq_calc" in sql
    assert "THEN 1 ELSE 0 END as revenue_acceleration_qoq_calc" in sql
