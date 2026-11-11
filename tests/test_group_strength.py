"""E2E for the group_strength_daily grid (VeraProjects#165).

Seeds ranks pcts, daily_metrics gate rows, and PIT classification for a 2-level
(sector + industry) x 3-group fixture including a sub-gate member and a
short-history ticker, runs transform 134, and asserts member_count, gate
exclusion, both method scores, per-(level,horizon) group_rank, rank_change_1d
across two sessions, and PIT membership (a member whose sector changed
mid-window counts under the right group per date).
"""

import math
from datetime import date, datetime
from pathlib import Path

import pytest

from sigmarail.database import execute_sql_file, get_project_root

D1 = date(1990, 1, 5)
D2 = date(1990, 1, 8)
CHUNK = ("1990-01-01", "1990-01-31")

# ticker -> all-four-horizon pct (None yearly = short history). One value used
# for every non-NULL horizon to keep hand-math tractable.
PCTS = {
    "GS_A": (0.90, 0.90, 0.90, 0.90),     # Tech, always counted
    "GS_B": (None, 0.70, 0.70, 0.70),     # Tech, short history — NULL perf_1y
    "GS_C": (0.85, 0.85, 0.85, 0.85),     # Tech but close=5 -> gated out
    "GS_D": (0.50, 0.50, 0.50, 0.50),     # Tech on D1 -> Energy on D2 (PIT)
    "GS_E": (0.95, 0.95, 0.95, 0.95),     # Energy
    "GS_F": (0.20, 0.20, 0.20, 0.20),     # Materials
}
# close, avg_vol_20d — dollar_vol = close*avg_vol_20d; gate needs >= $20M & close >= 10
GATE = {
    "GS_A": (50.0, 1_000_000), "GS_B": (50.0, 1_000_000), "GS_C": (5.0, 1_000_000),
    "GS_D": (50.0, 1_000_000), "GS_E": (50.0, 1_000_000), "GS_F": (50.0, 1_000_000),
}
SECTOR = {"GS_A": "Tech", "GS_B": "Tech", "GS_C": "Tech",
          "GS_D": "Tech", "GS_E": "Energy", "GS_F": "Materials"}
INDUSTRY = {"GS_A": "Software", "GS_B": "Software", "GS_C": "Software",
            "GS_D": "Software", "GS_E": "Oil", "GS_F": "Mining"}


def _transform_path(name: str) -> Path:
    root = Path(get_project_root())
    return root / "src" / "sigmarail" / "sql" / "schema" / name


@pytest.fixture(scope="module")
def grid(global_client):
    client = global_client
    root = Path(get_project_root())
    for name in (
        "205-schema-ticker_classification_daily.sql",
        "209-schema-group_strength_daily.sql",
    ):
        p = root / "src" / "sigmarail" / "sql" / "schema" / name
        assert p.is_file(), f"missing {name}"
        assert execute_sql_file(p, description=name)

    tickers = tuple(PCTS)
    client.command(
        "ALTER TABLE relative_strength_ranks DELETE WHERE ticker IN %(t)s",
        parameters={"t": tickers},
    )
    client.command(
        "ALTER TABLE daily_metrics DELETE WHERE ticker IN %(t)s",
        parameters={"t": tickers},
    )
    client.command(
        "ALTER TABLE ticker_classification_daily DELETE WHERE ticker IN %(t)s",
        parameters={"t": tickers},
    )
    client.command(
        "ALTER TABLE group_strength_daily DELETE WHERE date IN %(d)s",
        parameters={"d": (D1, D2)},
    )
    stamp = datetime(2030, 1, 1)  # freshness: always newer than prior emit
    client.insert(
        "relative_strength_ranks",
        [(t, d, y, p6, p3, p1, None, None, None, stamp)
         for t, (y, p6, p3, p1) in PCTS.items() for d in (D1, D2)],
        column_names=["ticker", "date", "yearly_pct", "performance_6m_pct",
                      "performance_3m_pct", "performance_1m_pct", "blended_pct",
                      "rs_rating", "momentum_rank", "lastupdated"],
    )
    client.insert(
        "daily_metrics",
        [(t, d, c, v, stamp)
         for t, (c, v) in GATE.items() for d in (D1, D2)],
        column_names=["ticker", "date", "close", "avg_vol_20d", "lastupdated"],
    )
    cls_rows = [
        (t, date(1970, 1, 1), SECTOR[t], INDUSTRY[t], "Fama",
         "sicS", "sicI", stamp)
        for t in PCTS
    ]
    # GS_D reclassifies Tech -> Energy on D2.
    cls_rows.append(("GS_D", D2, "Energy", "Oil", "Fama",
                     "sicS", "sicI", stamp))
    client.insert(
        "ticker_classification_daily",
        cls_rows,
        column_names=["ticker", "date", "sector", "industry", "famaindustry",
                      "sicsector", "sicindustry", "lastupdated"],
    )
    from sigmarail.transform_sql import run_transform_file

    run_transform_file(
        client,
        _transform_path("209-schema-group_strength_daily.sql"),
        {"chunk_start_date": CHUNK[0], "chunk_end_date": CHUNK[1]},
    )
    res = client.query(
        """
        SELECT date, level, group_name, horizon, member_count,
               score, score_mean, score_breadth, group_rank, rank_change_1d
        FROM group_strength_daily FINAL
        WHERE date IN %(d)s AND group_name IN ('Tech', 'Energy', 'Materials')
          AND level = 'sector'
        """,
        parameters={"d": (D1, D2)},
    )
    return {(r[0], r[2], r[3]): r[4:] for r in res.result_rows}


def _close(got: float | None, want: float) -> bool:
    return got is not None and math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-9)


def test_member_count_excludes_gated_and_null_pct(grid) -> None:
    # D1 perf_1y Tech: A + D (B NULL yearly, C gated) -> 2
    assert grid[(D1, "Tech", "perf_1y")][0] == 2
    # D1 perf_1m Tech: A + B + D -> 3
    assert grid[(D1, "Tech", "perf_1m")][0] == 3
    # Energy D1: only E -> 1; D2: D reclassified in -> 2
    assert grid[(D1, "Energy", "perf_1y")][0] == 1
    assert grid[(D2, "Energy", "perf_1y")][0] == 2


def test_method_scores(grid) -> None:
    # D1 Tech perf_1y: members A(.9) D(.5) -> mean .70, breadth 0.5 (A>=.8)
    _, score, mean, breadth = grid[(D1, "Tech", "perf_1y")][:4]
    assert _close(mean, 0.70)
    assert _close(breadth, 0.5)
    assert _close(score, 0.60)
    # Energy solo member .95 -> mean .95, breadth 1.0, score .975
    _, score, mean, breadth = grid[(D1, "Energy", "perf_1y")][:4]
    assert _close(mean, 0.95) and _close(breadth, 1.0) and _close(score, 0.975)


def test_group_rank_within_level_horizon(grid) -> None:
    # D1 perf_1y scores: Materials .10 < Tech .60 < Energy .975 -> 0, 50, 100
    assert _close(grid[(D1, "Materials", "perf_1y")][4], 0.0)
    assert _close(grid[(D1, "Tech", "perf_1y")][4], 50.0)
    assert _close(grid[(D1, "Energy", "perf_1y")][4], 100.0)


def test_rank_change_1d_across_sessions(grid) -> None:
    # D2 perf_1y: Materials .10 < Energy .6125 < Tech .95 -> ranks 0/50/100
    # Tech: 100 (D2) - 50 (D1) = +50; Energy: 50 - 100 = -50
    assert grid[(D2, "Tech", "perf_1y")][5] == 50
    assert grid[(D2, "Energy", "perf_1y")][5] == -50
    assert grid[(D1, "Tech", "perf_1y")][5] is None  # first session


def test_pit_membership_honored(grid) -> None:
    # GS_D counts under Tech on D1 (score .60 includes its .50) and under
    # Energy on D2 (Energy score .6125 = mean(.5,.95) blended w/ breadth .5).
    _, score, mean, breadth = grid[(D2, "Energy", "perf_1y")][:4]
    assert _close(mean, 0.725)
    assert _close(breadth, 0.5)
    assert _close(score, 0.6125)
    # D2 Tech perf_1y drops to just A: mean .9, breadth 1.0, score .95
    _, score, mean, breadth = grid[(D2, "Tech", "perf_1y")][:4]
    assert _close(mean, 0.9) and _close(breadth, 1.0) and _close(score, 0.95)
