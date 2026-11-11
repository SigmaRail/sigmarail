"""E2E for transform 55 → industry_group_strength (VeraProjects#182).

Executes the packaged industry-group transform through the
real populate body (chunk params and test-database routing) — the SQL must
parse and resolve end-to-end. A stale t.sicindustry alias escaped to prod
commit e827957 precisely because no test ran this transform.

Fixture: two sicindustry groups over two sessions; IG_D reclassifies
Software -> Oil on D2 (PIT assertion via the ASOF classification join).
"""

from datetime import date, datetime
from pathlib import Path

import pytest

from sigmarail.database import execute_sql_file, get_project_root

D1 = date(1990, 2, 5)
D2 = date(1990, 2, 6)
CHUNK = ("1990-02-01", "1990-02-28")

TICKERS = ("IG_A", "IG_B", "IG_C", "IG_D")

# rs_rating per ticker per date. Software avg D1 = (80+60+100)/3 = 80,
# Oil avg D1 = 40. D2 (IG_D now Oil): Software = (80+70)/2 = 75,
# Oil = (40+90)/2 = 65. Software strictly above Oil on both dates.
RS = {
    "IG_A": {D1: 80.0, D2: 80.0},
    "IG_B": {D1: 60.0, D2: 70.0},
    "IG_C": {D1: 40.0, D2: 40.0},
    "IG_D": {D1: 100.0, D2: 90.0},
}

# sicindustry membership: IG_D Software until D2, then Oil (PIT).
SIC = {"IG_A": "Software", "IG_B": "Software", "IG_C": "Oil"}


def _transform_path(name: str) -> Path:
    root = Path(get_project_root())
    return root / "src" / "sigmarail" / "sql" / "schema" / name


def _transform_body(name: str) -> str:
    raise AssertionError("use run_transform_file against the xform view path")


@pytest.fixture(scope="module")
def igs(global_client):
    client = global_client
    root = Path(get_project_root())
    for name in (
        "55-schema-industry-group-strength.sql",
        "205-schema-ticker_classification_daily.sql",
    ):
        p = root / "src" / "sigmarail" / "sql" / "schema" / name
        assert p.is_file(), f"missing {name}"
        assert execute_sql_file(p, description=name)

    client.command(
        "ALTER TABLE relative_strength DELETE WHERE ticker IN %(t)s",
        parameters={"t": TICKERS},
        settings={"mutations_sync": 2},
    )
    client.command(
        "ALTER TABLE industry_group_strength DELETE WHERE date IN %(d)s",
        parameters={"d": (D1, D2)},
        settings={"mutations_sync": 2},
    )
    client.command(
        "ALTER TABLE ticker_classification_daily DELETE WHERE ticker IN %(t)s",
        parameters={"t": TICKERS},
        settings={"mutations_sync": 2},
    )

    stamp = datetime(2030, 1, 1)  # freshness: always newer than prior emit
    client.insert(
        "relative_strength",
        [(t, d, i, r, stamp)
         for i, (t, dd) in enumerate(sorted(RS.items()))
         for d, r in dd.items()],
        column_names=["ticker", "date", "momentum_rank", "rs_rating", "lastupdated"],
    )
    cls_rows = [
        (t, date(1970, 1, 1), "S", "I", "F", "sicS", sic, stamp)
        for t, sic in SIC.items()
    ]
    cls_rows.append(("IG_D", date(1970, 1, 1), "S", "I", "F", "sicS",
                     "Software", stamp))
    cls_rows.append(("IG_D", D2, "S", "I", "F", "sicS",
                     "Oil", stamp))
    client.insert(
        "ticker_classification_daily",
        cls_rows,
        column_names=["ticker", "date", "sector", "industry", "famaindustry",
                      "sicsector", "sicindustry", "lastupdated"],
    )

    from sigmarail.transform_sql import run_transform_file

    run_transform_file(
        client,
        _transform_path("55-schema-industry-group-strength.sql"),
        {"chunk_start_date": CHUNK[0], "chunk_end_date": CHUNK[1]},
    )
    res = client.query(
        """
        SELECT date, industry, avg_rs_rating, industry_group_rank
        FROM industry_group_strength FINAL
        WHERE date IN (%(d1)s, %(d2)s)
          AND industry IN ('Software', 'Oil')
        """,
        parameters={"d1": D1, "d2": D2},
    )
    return {(r[0], r[1]): (r[2], r[3]) for r in res.result_rows}


def test_transform_executes(igs) -> None:
    assert igs, "transform 55 emitted no rows — SQL did not resolve/run"


def test_avg_rating_math(igs) -> None:
    assert igs[(D1, "Software")][0] == pytest.approx(80.0)
    assert igs[(D1, "Oil")][0] == pytest.approx(40.0)
    assert igs[(D2, "Software")][0] == pytest.approx(75.0)
    assert igs[(D2, "Oil")][0] == pytest.approx(65.0)


def test_pit_reclassification(igs) -> None:
    """IG_D counts toward Software on D1 (members=3) and Oil on D2 (members=2).
    If ASOF resolved the seed row instead of the D2 row, Oil's D2 avg would be
    (40+100)/2=70 -> 65 vs 70 distinguishes it."""
    assert igs[(D2, "Oil")][0] == pytest.approx(65.0)


def test_group_rank_ordering(igs) -> None:
    for d in (D1, D2):
        assert igs[(d, "Software")][1] > igs[(d, "Oil")][1]
