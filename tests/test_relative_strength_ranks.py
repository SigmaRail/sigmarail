"""E2E tests for transform 49 (relative_strength_ranks) NULL policy.

VeraProjects#159: a NULL horizon perf must emit a NULL pct — never a rank.
Unguarded row_number() ordered NULLs last, so missing history ranked in the
top band (~97th pct) and the coalesce() fallback chain never fired.

Seeds a controlled stocks-pool cohort on an unused 1990 date, runs the real
transform body for one chunk, and asserts exact percentile math:

- NULL perf -> NULL pct (short-history ticker's 1y pct is NULL, not ~0.97)
- blended_pct renormalizes weights over available components
- percentile denominators count only non-NULL rows (valid members unchanged)
- all-NULL row -> NULL pcts/blend/rs_rating; momentum_rank ranks it last
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

import clickhouse_connect
import pytest

from sigmarail.config import get_project_root
from sigmarail.database import execute_sql_file

SEED_DATE = date(1990, 1, 5)
CHUNK = ("1990-01-01", "1990-01-31")
POOL = "stocks"

# Second date (same chunk): a funds-only member plus a ticker staged in BOTH
# pools — #174: percentiles rank one shared universe, and a dual-pool ticker
# must emit exactly one row.
SEED_DATE2 = date(1990, 1, 8)
DUAL_COHORT = {
    "RS_S": ("stocks", (0.10, 0.09, 0.08, 0.07)),  # lowest on every horizon
    "RS_F": ("funds", (0.20, 0.19, 0.18, 0.17)),   # funds-only member, mid
}
DUAL_TICKER = "RS_DUAL"
DUAL_PERFS = (0.30, 0.29, 0.28, 0.27)              # strongest on every horizon

# (ticker, yearly, p6m, p3m, p1m) — yearly=None marks the short-history row.
# RS_SHORT sits mid-pack on every sub-horizon (BLLN analog): strong enough to
# rank, never top band.
COHORT = {
    "RS_LONG_A": (0.50, 0.45, 0.40, 0.35),  # strongest on every horizon
    "RS_SHORT": (None, 0.15, 0.10, 0.07),  # BLLN-style: no 1y, mid subs
    "RS_LONG_B": (0.30, 0.25, 0.20, 0.15),
    "RS_LONG_C": (0.10, 0.08, 0.06, 0.05),
    "RS_LONG_D": (-0.05, -0.02, -0.03, -0.04),
    "RS_NULL_Z": (None, None, None, None),  # no history at all
}
TICKERS = tuple(COHORT)

# Percentile truth computed by hand (asc order, (rn-1)/(count_nonnull-1)):
# yearly has 4 non-NULL members; each sub-horizon has 5 (D<C<SHORT<B<A).
YEARLY_PCT = {
    "RS_LONG_D": 0.0,
    "RS_LONG_C": 1 / 3,
    "RS_LONG_B": 2 / 3,
    "RS_LONG_A": 1.0,
}
P6M = {
    "RS_LONG_D": 0.0,
    "RS_LONG_C": 0.25,
    "RS_SHORT": 0.5,
    "RS_LONG_B": 0.75,
    "RS_LONG_A": 1.0,
}
P3M = {
    "RS_LONG_D": 0.0,
    "RS_LONG_C": 0.25,
    "RS_SHORT": 0.5,
    "RS_LONG_B": 0.75,
    "RS_LONG_A": 1.0,
}
P1M = {
    "RS_LONG_D": 0.0,
    "RS_LONG_C": 0.25,
    "RS_SHORT": 0.5,
    "RS_LONG_B": 0.75,
    "RS_LONG_A": 1.0,
}

# blend = (0.4*y + 0.2*p6 + 0.2*p3 + 0.2*p1) / (0.4*(y!=NULL) + 0.2*(p6|y) + 0.2*(p3|y) + 0.2*(p1|y))
BLENDED = {
    "RS_LONG_A": 1.0,
    "RS_SHORT": (0.2 * 0.5 * 3) / 0.6,  # 0.5 — renorm over subs
    "RS_LONG_B": (0.4 * (2 / 3) + 0.2 * 0.75 * 3) / 1.0,  # 0.7166…
    "RS_LONG_C": (0.4 * (1 / 3) + 0.2 * 0.25 * 3) / 1.0,  # 0.2833…
    "RS_LONG_D": 0.0,
}
# rs_rating: blend asc over 5 non-NULL members, (rn-1)/4*100
RS_RATING = {
    "RS_LONG_D": 0.0,
    "RS_LONG_C": 25.0,
    "RS_SHORT": 50.0,
    "RS_LONG_B": 75.0,
    "RS_LONG_A": 100.0,
}
MOMENTUM = {
    "RS_LONG_A": 1,
    "RS_LONG_B": 2,
    "RS_SHORT": 3,
    "RS_LONG_C": 4,
    "RS_LONG_D": 5,
    "RS_NULL_Z": 6,
}


def _run_transform(client, name: str = "49-schema-relative_strength_ranks.sql", **params) -> None:
    """Register the transform view and insert through it for the given chunk."""
    from sigmarail.transform_sql import run_transform_file

    root = Path(get_project_root())
    run_transform_file(client, root / "src" / "sigmarail" / "sql" / "schema" / name, params)


def _ensure_schema(client) -> None:
    root = Path(get_project_root())
    for name in (
        "48-schema-relative_strength_base.sql",
        "49-schema-relative_strength_ranks.sql",
    ):
        path = root / "src" / "sigmarail" / "sql" / "schema" / name
        assert path.is_file(), f"missing schema {path}"
        assert execute_sql_file(path, description=name), f"failed to load {name}"


def _seed_base(client) -> None:
    # lastupdated must move forward on re-seed: relative_strength_base is
    # ReplacingMergeTree(lastupdated) and the transform only emits chunks whose
    # source watermark advanced.
    stamp = datetime.now()
    rows = [
        (t, SEED_DATE, y, p6, p3, p1, 1.0, POOL, stamp)
        for t, (y, p6, p3, p1) in COHORT.items()
    ]
    rows += [
        (t, SEED_DATE2, y, p6, p3, p1, 1.0, pool, stamp)
        for t, (pool, (y, p6, p3, p1)) in DUAL_COHORT.items()
    ]
    # Same (ticker, date) in both pools — the historical dual-emit case.
    rows += [
        (DUAL_TICKER, SEED_DATE2, *DUAL_PERFS, 1.0, pool, stamp)
        for pool in ("stocks", "funds")
    ]
    client.insert(
        "relative_strength_base",
        rows,
        column_names=[
            "ticker",
            "date",
            "yearly_performance",
            "performance_6m",
            "performance_3m",
            "performance_1m",
            "price_relative_ratio",
            "pool",
            "lastupdated",
        ],
    )


@pytest.fixture(scope="module")
def ranks_mart(global_client: clickhouse_connect.driver.Client):
    client = global_client
    _ensure_schema(client)
    _seed_base(client)
    # The freshness gate is date-granular: any row in the chunk with a newer
    # lastupdated (e.g. test_group_strength's 2030-01-01 freshness stamps at
    # the same 1990 dates) silences the transform for every ticker that day.
    client.command(
        "ALTER TABLE relative_strength_ranks DELETE "
        "WHERE date BETWEEN %(s)s AND %(e)s SETTINGS mutations_sync=2",
        parameters={"s": CHUNK[0], "e": CHUNK[1]},
    )
    _run_transform(client, chunk_start_date=CHUNK[0], chunk_end_date=CHUNK[1])
    res = client.query(
        """
        SELECT ticker, yearly_pct, performance_6m_pct, performance_3m_pct,
               performance_1m_pct, blended_pct, rs_rating, momentum_rank
        FROM relative_strength_ranks FINAL
        WHERE date = %(d)s AND ticker IN %(t)s
        """,
        parameters={"d": SEED_DATE, "t": TICKERS},
    )
    return {r[0]: r[1:] for r in res.result_rows}


def _close(got: float | None, want: float) -> bool:
    return got is not None and math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-9)


def test_all_seeded_rows_emitted(ranks_mart) -> None:
    assert set(ranks_mart) == set(TICKERS)


def test_null_perf_produces_null_pct(ranks_mart) -> None:
    assert ranks_mart["RS_SHORT"][0] is None, (
        "short-history yearly_pct must be NULL, not top-band"
    )
    assert all(v is None for v in ranks_mart["RS_NULL_Z"][:5]), (
        "all-NULL row must emit NULL pcts/blend"
    )


def test_valid_members_unchanged_by_null_rows(ranks_mart) -> None:
    """Denominator counts only non-NULL perfs: valid rows keep exact 0..1 spread."""
    for t, want in YEARLY_PCT.items():
        assert _close(ranks_mart[t][0], want), (
            f"{t} yearly_pct={ranks_mart[t][0]}, want {want}"
        )


def test_subhorizon_pcts_match_truth(ranks_mart) -> None:
    for pmap, idx in ((P6M, 1), (P3M, 2), (P1M, 3)):
        for t, want in pmap.items():
            assert _close(ranks_mart[t][idx], want), (
                f"{t} pct[{idx}]={ranks_mart[t][idx]}, want {want}"
            )


def test_blend_renormalizes_over_available_components(ranks_mart) -> None:
    """RS_SHORT: 1y weight leaves the denominator — blend = 0.3/0.6, not /1.0."""
    for t, want in BLENDED.items():
        assert _close(ranks_mart[t][4], want), (
            f"{t} blended_pct={ranks_mart[t][4]}, want {want}"
        )


def test_rs_rating_short_history_not_top_band(ranks_mart) -> None:
    """Bug symptom: BLLN-class tickers ranked ~97+ pts. RS_SHORT must rank by
    real sub-horizon history only (75th), not top band."""
    got = ranks_mart["RS_SHORT"][5]
    assert got is not None and got < 90, f"RS_SHORT rs_rating={got} still in top band"
    for t, want in RS_RATING.items():
        assert _close(ranks_mart[t][5], want), (
            f"{t} rs_rating={ranks_mart[t][5]}, want {want}"
        )


def test_all_null_row_null_rating_last_momentum(ranks_mart) -> None:
    row = ranks_mart["RS_NULL_Z"]
    assert row[5] is None, "all-NULL row must carry NULL rs_rating"
    assert row[6] == MOMENTUM["RS_NULL_Z"], (
        "all-NULL row ranks last (non-Nullable UInt32 downstream)"
    )


def test_momentum_rank_orders_by_blended(ranks_mart) -> None:
    for t, want in MOMENTUM.items():
        assert ranks_mart[t][6] == want, (
            f"{t} momentum_rank={ranks_mart[t][6]}, want {want}"
        )


@pytest.fixture(scope="module")
def dual_mart(ranks_mart, global_client):
    # Depends on ranks_mart so the chunk transform has already run.
    res = global_client.query(
        """
        SELECT ticker, yearly_pct, blended_pct, rs_rating, momentum_rank,
               count() OVER () AS n
        FROM relative_strength_ranks FINAL
        WHERE date = %(d)s AND ticker IN %(t)s
        """,
        parameters={"d": SEED_DATE2, "t": tuple(DUAL_COHORT) + (DUAL_TICKER,)},
    )
    return res.result_rows


def test_dual_pool_ticker_emits_exactly_one_row(dual_mart) -> None:
    """#174: the same instrument staged in stocks AND funds collapses to one
    deterministic emit — never two rows racing ReplacingMergeTree."""
    dual_rows = [r for r in dual_mart if r[0] == DUAL_TICKER]
    assert len(dual_rows) == 1, f"RS_DUAL emitted {len(dual_rows)} rows"


def test_shared_universe_percentiles(dual_mart) -> None:
    """Funds rows rank inside the shared cohort: RS_F is mid of 3, not bottom
    of a 2-member funds pool (segmented code would emit 0.0)."""
    got = {r[0]: r[1:] for r in dual_mart}
    assert _close(got["RS_S"][0], 0.0)
    assert _close(got["RS_F"][0], 0.5)
    assert _close(got[DUAL_TICKER][0], 1.0)
    assert _close(got["RS_S"][2], 0.0)
    assert _close(got["RS_F"][2], 50.0)
    assert _close(got[DUAL_TICKER][2], 100.0)
    assert got[DUAL_TICKER][3] == 1
    assert got["RS_F"][3] == 2
    assert got["RS_S"][3] == 3


@pytest.fixture(scope="module")
def rs_mart(ranks_mart, global_client):
    """Publish per-horizon ratings declared in the current table snapshot."""
    client = global_client
    # Same date-granular gate on transform 50's target — clear the chunk.
    client.command(
        "ALTER TABLE relative_strength DELETE "
        "WHERE date BETWEEN %(s)s AND %(e)s SETTINGS mutations_sync=2",
        parameters={"s": CHUNK[0], "e": CHUNK[1]},
    )
    _run_transform(
        client,
        "50-schema-relative_strength.sql",
        chunk_start_date=CHUNK[0],
        chunk_end_date=CHUNK[1],
    )
    res = client.query(
        """
        SELECT ticker, rs_rating, rs_rating_12m, rs_rating_6m,
               rs_rating_3m, rs_rating_1m
        FROM relative_strength FINAL
        WHERE date = %(d)s AND ticker IN %(t)s
        """,
        parameters={"d": SEED_DATE, "t": TICKERS},
    )
    return {r[0]: r[1:] for r in res.result_rows}


def test_horizon_ratings_equal_component_pct_x100(rs_mart, ranks_mart) -> None:
    """rs_rating_3m == performance_3m_pct * 100 (0-100 publish of the same pct)."""
    for t, row in rs_mart.items():
        p3m_pct = ranks_mart[t][2]
        want = None if p3m_pct is None else p3m_pct * 100
        if want is None:
            assert row[3] is None, f"{t} rs_rating_3m={row[3]}, want NULL"
        else:
            assert _close(row[3], want), f"{t} rs_rating_3m={row[3]}, want {want}"


def test_null_component_publishes_null_rating(rs_mart) -> None:
    """RS_SHORT has no 1y history -> rs_rating_12m NULL, subs still publish."""
    assert rs_mart["RS_SHORT"][1] is None
    assert _close(rs_mart["RS_SHORT"][3], 50.0)
    assert all(v is None for v in rs_mart["RS_NULL_Z"]), "all-NULL -> all NULL"
