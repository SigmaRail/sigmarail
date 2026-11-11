"""L1 daily_prices / daily_valuation checks against the disposable sigmarail_test DB."""

from __future__ import annotations

import os

import clickhouse_connect
import pytest

from sigmarail.database import load_schema
from sigmarail.populate import DataPopulator


def _exists(client: clickhouse_connect.driver.Client, name: str) -> bool:
    db = str(client.query("SELECT currentDatabase()").result_rows[0][0])
    n = int(
        client.query(
            "SELECT count() FROM system.tables WHERE database = {db:String} AND name = {n:String}",
            parameters={"db": db, "n": name},
        ).result_rows[0][0]
    )
    return n == 1


@pytest.fixture(scope="module")
def ensure_l1_prices(global_client: clickhouse_connect.driver.Client) -> None:
    for t in ("daily_prices", "daily_valuation"):
        if not _exists(global_client, t):
            assert load_schema(), "load_schema failed for Episode B L1 tables"
    start = os.environ.get("SIGMARAIL_TEST_POPULATE_START", "2024-12-01")
    end = os.environ.get("SIGMARAIL_TEST_POPULATE_END", "2024-12-31")
    # Prefer short end of fixture if metrics exist
    mx = global_client.query("SELECT toString(max(date)) FROM sep").result_rows[0][0]
    if mx:
        end = mx
        start = global_client.query(
            "SELECT toString(greatest(toDate('2024-12-01'), toDate({e:String}) - 14))",
            parameters={"e": end},
        ).result_rows[0][0]
    if int(global_client.query("SELECT count() FROM daily_prices").result_rows[0][0]) == 0:
        pop = DataPopulator()
        assert pop.populate_metrics(
            start_date=start,
            end_date=end,
            metrics_to_process=["daily_prices", "daily_valuation"],
            force_refresh=True,
        )


def test_daily_prices_schema(global_client, ensure_l1_prices: None) -> None:
    assert _exists(global_client, "daily_prices")
    assert _exists(global_client, "daily_valuation")


def test_daily_prices_matches_sep_for_aapl(
    global_client, ensure_l1_prices: None
) -> None:
    row = global_client.query(
        """
        SELECT
            p.close, p.closeadj, s.close, s.closeadj
        FROM daily_prices AS p FINAL
        INNER JOIN sep AS s FINAL
            ON p.ticker = s.ticker AND p.date = s.date
        WHERE p.ticker = 'AAPL' AND p.source_table = 'SEP'
        ORDER BY p.date DESC
        LIMIT 1
        """
    ).result_rows
    if not row:
        pytest.skip("no overlapping AAPL daily_prices/sep row")
    pc, pca, sc, sca = row[0]
    assert float(pc) == pytest.approx(float(sc), rel=1e-9, abs=1e-9)
    assert float(pca) == pytest.approx(float(sca), rel=1e-9, abs=1e-9)


def test_daily_valuation_matches_sharadar_daily(
    global_client, ensure_l1_prices: None
) -> None:
    row = global_client.query(
        """
        SELECT v.pe, d.pe, v.marketcap, d.marketcap
        FROM daily_valuation AS v FINAL
        INNER JOIN daily AS d FINAL
            ON v.ticker = d.ticker AND v.date = d.date
        WHERE v.ticker = 'AAPL'
        ORDER BY v.date DESC
        LIMIT 1
        """
    ).result_rows
    if not row:
        pytest.skip("no overlapping AAPL daily_valuation/daily row")
    vpe, dpe, vmc, dmc = row[0]
    if vpe is not None and dpe is not None:
        assert float(vpe) == pytest.approx(float(dpe), rel=1e-9, abs=1e-9)
    if vmc is not None and dmc is not None:
        assert float(vmc) == pytest.approx(float(dmc), rel=1e-9, abs=1e-9)
