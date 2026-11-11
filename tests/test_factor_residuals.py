"""
Golden + sanity tests for factor_residuals (stage-2 rolling OLS).

Populates asset-returns-daily → sector-factor-residuals → factor-residuals on demand,
then compares one window=60 row against a NumPy least-squares OLS oracle on the same (y, x1, x2) window.
"""

from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd
import pytest
import clickhouse_connect

from sigmarail.populate import DataPopulator

SECTOR_ETF_SQL = """
multiIf(
  t.sector = 'Technology',             'XLK',
  t.sector = 'Healthcare',             'XLV',
  t.sector = 'Financial Services',     'XLF',
  t.sector = 'Consumer Cyclical',      'XLY',
  t.sector = 'Consumer Defensive',     'XLP',
  t.sector = 'Industrials',            'XLI',
  t.sector = 'Energy',                 'XLE',
  t.sector = 'Utilities',              'XLU',
  t.sector = 'Real Estate',            'XLRE',
  t.sector = 'Communication Services', 'XLC',
  t.sector = 'Basic Materials',        'XLB',
  '')
"""


def _populate_start_end() -> tuple[str, str]:
    start = os.environ.get("SIGMARAIL_TEST_POPULATE_START", "2021-01-01")
    end = os.environ.get("SIGMARAIL_TEST_POPULATE_END", "2024-12-31")
    return start, end


def _close(a: float, b: float, *, rtol: float = 1e-5, atol: float = 1e-4) -> bool:
    return bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) <= atol + rtol * abs(b))


@pytest.fixture(scope="module")
def ensure_factor_chain(global_client: clickhouse_connect.driver.Client) -> None:
    """Ensure stage-1/2 factor tables are populated in the test database."""
    cnt = int(
        global_client.query(
            "SELECT count() FROM factor_residuals WHERE window = 60"
        ).result_rows[0][0]
    )
    if cnt > 0:
        return

    ard_cnt = int(global_client.query("SELECT count() FROM asset_returns_daily").result_rows[0][0])
    if ard_cnt == 0:
        pytest.skip("asset_returns_daily empty; cannot validate factor_residuals")

    start, end = _populate_start_end()
    pop = DataPopulator()
    ok = pop.populate_metrics(
        start_date=start,
        end_date=end,
        metrics_to_process=[
            "asset-returns-daily",
            "sector-factor-residuals",
            "factor-residuals",
        ],
        force_refresh=True,
    )
    assert ok, "Failed to populate factor residual chain in test mode"

    cnt2 = int(
        global_client.query(
            "SELECT count() FROM factor_residuals WHERE window = 60"
        ).result_rows[0][0]
    )
    assert cnt2 > 0, "factor_residuals still empty after populate"


def _pick_golden_row(client: clickhouse_connect.driver.Client) -> pd.Series:
    df = client.query_df(
        """
        SELECT ticker, toString(date) AS date, rolling_alpha, alpha_tstat,
               beta_mkt, beta_sector, residual, r2, n_obs
        FROM factor_residuals FINAL
        WHERE window = 60 AND n_obs = 60
          AND isFinite(rolling_alpha) AND isFinite(alpha_tstat)
          AND isFinite(beta_mkt) AND isFinite(beta_sector)
          AND isFinite(residual)
        ORDER BY date DESC, ticker
        LIMIT 1
        """
    )
    assert not df.empty, "No suitable window=60 row for golden OLS check"
    return df.iloc[0]


def _load_regression_window(
    client: clickhouse_connect.driver.Client,
    *,
    ticker: str,
    as_of: str,
    window: int = 60,
) -> pd.DataFrame:
    q = f"""
    WITH
      spy AS (
        SELECT date, toFloat64(close_ret - cash_ret) AS x1
        FROM asset_returns_daily FINAL
        WHERE ticker = 'SPY'
      ),
      sector_etf AS (
        SELECT {SECTOR_ETF_SQL} AS etf
        FROM tickers AS t FINAL
        WHERE t.ticker = {{ticker:String}}
        LIMIT 1
      )
    SELECT
      r.date AS date,
      toFloat64(r.close_ret - r.cash_ret) AS y,
      spy.x1 AS x1,
      toFloat64(sfr.sector_orth) AS x2
    FROM asset_returns_daily AS r FINAL
    INNER JOIN spy ON spy.date = r.date
    INNER JOIN sector_etf ON 1
    INNER JOIN sector_factor_residuals_daily AS sfr FINAL
      ON sfr.date = r.date
     AND sfr.etf_ticker = sector_etf.etf
     AND sfr.window = {{window:UInt16}}
    WHERE r.ticker = {{ticker:String}}
      AND r.date <= toDate({{as_of:String}})
    ORDER BY r.date DESC
    LIMIT {{window:UInt16}}
    """
    df = client.query_df(
        q,
        parameters={"ticker": ticker, "as_of": as_of, "window": window},
    )
    assert len(df) == window, f"Expected {window} rows for {ticker} @ {as_of}, got {len(df)}"
    return df.sort_values("date").reset_index(drop=True)


def test_schema_has_expected_columns(global_client: clickhouse_connect.driver.Client) -> None:
    names = set(global_client.query_df("DESCRIBE factor_residuals")["name"].astype(str))
    for col in (
        "date",
        "ticker",
        "window",
        "residual",
        "rolling_alpha",
        "alpha_tstat",
        "beta_mkt",
        "beta_sector",
        "r2",
        "n_obs",
        "lastupdated",
    ):
        assert col in names, f"Missing column factor_residuals.{col}"


def test_scalemarketcap_distinct_format(global_client: clickhouse_connect.driver.Client) -> None:
    rows = global_client.query(
        """
        SELECT DISTINCT scalemarketcap
        FROM tickers FINAL
        WHERE category = 'Domestic Common Stock' AND scalemarketcap != ''
        ORDER BY 1
        """
    ).result_rows
    assert rows, "No scalemarketcap values for Domestic Common Stock"
    pattern = re.compile(r"^\d+ - ")
    bad = [r[0] for r in rows if not pattern.match(str(r[0]))]
    assert not bad, f"scalemarketcap values not matching 'N - Label': {bad[:5]}"


def test_golden_ols_matches_numpy_reference(
    global_client: clickhouse_connect.driver.Client,
    ensure_factor_chain: None,
) -> None:
    row = _pick_golden_row(global_client)
    win = _load_regression_window(
        global_client,
        ticker=str(row["ticker"]),
        as_of=str(row["date"]),
        window=60,
    )
    y = win["y"].to_numpy(dtype=float)
    x1 = win["x1"].to_numpy(dtype=float)
    x2 = win["x2"].to_numpy(dtype=float)

    x = np.column_stack([np.ones(len(y)), x1, x2])
    params, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ params
    dof = len(y) - x.shape[1]
    residual_variance = float(residuals @ residuals) / dof
    covariance = residual_variance * np.linalg.inv(x.T @ x)
    t_values = params / np.sqrt(np.diag(covariance))

    assert _close(float(row["rolling_alpha"]), float(params[0]))
    assert _close(float(row["beta_mkt"]), float(params[1]))
    assert _close(float(row["beta_sector"]), float(params[2]))
    assert _close(float(row["alpha_tstat"]), float(t_values[0]))
    assert _close(float(row["residual"]), float(residuals[-1]))


def test_beta_mkt_sanity_sample(
    global_client: clickhouse_connect.driver.Client,
    ensure_factor_chain: None,
) -> None:
    df = global_client.query_df(
        """
        SELECT beta_mkt
        FROM factor_residuals FINAL
        WHERE window = 60 AND isFinite(beta_mkt)
        ORDER BY rand()
        LIMIT 5000
        """
    )
    assert not df.empty
    med = float(df["beta_mkt"].median())
    assert 0.2 < med < 3.5, f"Median beta_mkt {med} outside plausible range"


def test_ols_matches_numpy_oracle_across_sample(
    global_client: clickhouse_connect.driver.Client,
    ensure_factor_chain: None,
) -> None:
    """Cross-validate SQL rolling OLS against numpy.linalg.lstsq (LAPACK) on a
    sample of tickers and windows.

    Expected values are computed by the vetted NumPy library from the same
    (y, x1, x2) window ClickHouse used, so the SQL formula must match the
    reference regression coefficient-by-coefficient. This is the strongest
    check of the math: it fails if the SQL closed-form OLS drifts from the
    reference least-squares solution.
    """
    rows = global_client.query_df(
        """
        SELECT ticker, toString(date) AS date, window,
               rolling_alpha, alpha_tstat, beta_mkt, beta_sector, residual
        FROM (
            SELECT ticker, date, window,
                   rolling_alpha, alpha_tstat, beta_mkt, beta_sector, residual
            FROM factor_residuals FINAL
            WHERE n_obs = window
              AND isFinite(rolling_alpha) AND isFinite(alpha_tstat)
              AND isFinite(beta_mkt) AND isFinite(beta_sector)
              AND isFinite(residual)
              AND date >= toDate('2024-06-01')
        )
        ORDER BY date, ticker, window
        """
    )
    assert len(rows) >= 8, f"Need a populated sample for oracle check, got {len(rows)}"

    # Deterministic, window-balanced sample across tickers and both windows.
    rng = np.random.default_rng(7)
    by_window = {w: g.reset_index(drop=True) for w, g in rows.groupby("window")}
    sampled_rows = []
    max_per = 4
    for w, g in by_window.items():
        idx = rng.choice(len(g), size=min(max_per, len(g)), replace=False)
        sampled_rows.append(g.iloc[idx])
    sampled = pd.concat(sampled_rows).reset_index(drop=True).head(8)
    assert not sampled.empty

    for _, row in sampled.iterrows():
        ticker = str(row["ticker"])
        as_of = str(row["date"])
        window = int(row["window"])
        win = _load_regression_window(
            global_client, ticker=ticker, as_of=as_of, window=window
        )
        y = win["y"].to_numpy(dtype=float)
        x1 = win["x1"].to_numpy(dtype=float)
        x2 = win["x2"].to_numpy(dtype=float)

        x = np.column_stack([np.ones(len(y)), x1, x2])
        params, *_ = np.linalg.lstsq(x, y, rcond=None)
        residuals = y - x @ params
        dof = len(y) - x.shape[1]
        residual_variance = float(residuals @ residuals) / dof
        covariance = residual_variance * np.linalg.inv(x.T @ x)
        t_values = params / np.sqrt(np.diag(covariance))

        context = f"{ticker} @ {as_of} window={window}"
        assert _close(float(row["rolling_alpha"]), float(params[0])), f"alpha {context}"
        assert _close(float(row["beta_mkt"]), float(params[1])), f"beta_mkt {context}"
        assert _close(float(row["beta_sector"]), float(params[2])), f"beta_sector {context}"
        assert _close(float(row["alpha_tstat"]), float(t_values[0])), f"alpha_tstat {context}"
        assert _close(float(row["residual"]), float(residuals[-1])), f"residual {context}"


def test_alpha_tstat_mostly_finite_after_warmup(
    global_client: clickhouse_connect.driver.Client,
    ensure_factor_chain: None,
) -> None:
    start, end = _populate_start_end()
    row = global_client.query(
        f"""
        SELECT
          count() AS n,
          countIf(NOT isFinite(alpha_tstat)) AS bad
        FROM factor_residuals FINAL
        WHERE window = 60
          AND date >= toDate('{start}') + 90
          AND date <= toDate('{end}')
        """
    ).result_rows[0]
    n, bad = int(row[0]), int(row[1])
    assert n > 0
    assert bad / n < 0.05, f"Too many non-finite alpha_tstat: {bad}/{n}"
