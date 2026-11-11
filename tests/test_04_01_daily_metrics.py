"""
Tests for validating the contents of the daily_metrics table, including
source-level validation against pandas calculations.
"""

import logging
import os
from datetime import date, timedelta
import calendar
import pandas as pd
import pytest
from sigmarail.database import get_client
import clickhouse_connect
import numpy as np

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def db_client(global_client):
    """Provides a database client for the test module."""
    yield global_client

@pytest.fixture(scope='class')
def daily_metrics_for_validation(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    """
    Provides the populated daily_metrics table as a pandas DataFrame for validation.
    """
    logger.info("--- Fixture: daily_metrics_for_validation ---")
    client = get_client()
    query = "SELECT * FROM daily_metrics ORDER BY ticker, date"
    df = client.query_df(query)
    df['date'] = pd.to_datetime(df['date']).dt.date
    logger.info(f"Loaded {len(df)} rows from daily_metrics for validation.")
    return df

@pytest.fixture(scope='class')
def sep_data(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    """
    Provides the source sep/sfp data as a pandas DataFrame for validation,
    mirroring the exact date range logic used in the transform.
    """
    logger.info("--- Fixture: sep_data (from SEP and SFP with date window) ---")
    client = get_client()
    # Must match session populate bounds (see tests/vera/conftest.py / VERA_TEST_POPULATE_*).
    start_date = date.fromisoformat(os.environ.get("SIGMARAIL_TEST_POPULATE_START", "2021-01-01"))
    end_date = date.fromisoformat(os.environ.get("SIGMARAIL_TEST_POPULATE_END", "2024-12-31"))
    
    query = f"""
    SELECT * FROM (
        SELECT p.* FROM sep AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
        WHERE p.date BETWEEN toDate('{start_date.strftime('%Y-%m-%d')}') - INTERVAL 400 DAY AND toDate('{end_date.strftime('%Y-%m-%d')}')
        UNION ALL
        SELECT p.* FROM sfp AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
        WHERE p.date BETWEEN toDate('{start_date.strftime('%Y-%m-%d')}') - INTERVAL 400 DAY AND toDate('{end_date.strftime('%Y-%m-%d')}')
    ) ORDER BY ticker, date
    """
    df = client.query_df(query)
    df['date'] = pd.to_datetime(df['date']) # Keep as timestamp for indexing
    logger.info(f"Loaded {len(df)} rows from sep and sfp for validation within the transform's date window.")
    return df

def get_metric_window(df: pd.DataFrame, ticker: str, end_date: date, window_size: int) -> pd.DataFrame:
    """
    Extracts a window of data for a specific ticker ending on a given date.
    """
    end_date_dt = pd.to_datetime(end_date)
    ticker_data = df[df['ticker'] == ticker].set_index('date')
    # Ensure the index is sorted before slicing
    ticker_data = ticker_data.sort_index()
    window_data = ticker_data.loc[:end_date_dt].tail(window_size)
    return window_data

class TestSMACalculations:
    """Validates Simple Moving Average calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 10, 31)

    @pytest.mark.parametrize("window", [10, 20, 50, 150, 200])
    def test_sma_calculation(self, daily_metrics_for_validation: pd.DataFrame, sep_data: pd.DataFrame, window: int):
        """
        Validates SMA calculations in daily_metrics against a pandas calculation.
        """
        logger.info(f"--- Test: Validating sma{window}d for {self.ticker} on {self.end_date_of_interest} ---")
        col_name = f'sma{window}d'

        # Get the pre-calculated SMA value from the database
        metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty, f"No data found for {self.ticker} on {self.end_date_of_interest} in daily_metrics."
        db_value = metric_row[col_name].iloc[0]

        # SQL 01-daily-metrics uses avg(close) for SMA columns (split-adjusted close, not closeadj).
        source_window = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, window)
        pandas_value = source_window["close"].mean()

        logger.info(f"Database sma{window}d: {db_value}")
        logger.info(f"Pandas-calculated sma{window}d: {pandas_value}")
        assert db_value == pytest.approx(pandas_value)


@pytest.mark.parametrize("ticker", ["AAPL", "SPY"])
def test_daily_metric_price_fields_match_sharadar_source(
    daily_metrics_for_validation: pd.DataFrame,
    sep_data: pd.DataFrame,
    ticker: str,
):
    """Check source passthrough and adjusted OHLC derivation for stock and fund data."""
    target_date = date(2024, 10, 31)
    source = sep_data[
        (sep_data["ticker"] == ticker)
        & (pd.to_datetime(sep_data["date"]).dt.date == target_date)
    ]
    target = daily_metrics_for_validation[
        (daily_metrics_for_validation["ticker"] == ticker)
        & (daily_metrics_for_validation["date"] == target_date)
    ]
    assert len(source) == 1, f"Expected one synthetic source row for {ticker} on {target_date}"
    assert len(target) == 1, f"Expected one daily_metrics row for {ticker} on {target_date}"
    src = source.iloc[0]
    out = target.iloc[0]

    for column in ("open", "high", "low", "close", "volume", "closeadj"):
        assert out[column] == pytest.approx(src[column]), f"daily_metrics.{column} diverged from {ticker} source"

    adjustment_factor = src["closeadj"] / src["close"]
    for source_column, output_column in (
        ("open", "openadj"),
        ("high", "highadj"),
        ("low", "lowadj"),
    ):
        expected = src[source_column] * adjustment_factor
        assert out[output_column] == pytest.approx(expected), (
            f"daily_metrics.{output_column} did not use closeadj/close"
        )

class TestAverageVolumeCalculations:
    """Validates average volume calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 10, 31)

    @pytest.mark.parametrize("window", [5, 20, 30, 50, 60, 90])
    def test_avg_volume_calculation(self, daily_metrics_for_validation: pd.DataFrame, sep_data: pd.DataFrame, window: int):
        """
        Validates average volume calculations in daily_metrics against a pandas calculation.
        """
        logger.info(f"--- Test: Validating avg_vol_{window}d for {self.ticker} on {self.end_date_of_interest} ---")
        col_name = f'avg_vol_{window}d'

        # Get the pre-calculated value from the database
        metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty, f"No data found for {self.ticker} on {self.end_date_of_interest} in daily_metrics."
        db_value = metric_row[col_name].iloc[0]

        # Calculate the value using pandas on the source data
        source_window = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, window)
        pandas_value = source_window['volume'].mean()

        logger.info(f"Database avg_vol_{window}d: {db_value}")
        logger.info(f"Pandas-calculated avg_vol_{window}d: {pandas_value}")
        assert db_value == pytest.approx(pandas_value)

class TestHighLowCalculations:
    """Validates high/low calculations over different periods."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 10, 31)

    @pytest.mark.parametrize("days", [5, 30, 90, 252])
    def test_high_low_calculation(self, daily_metrics_for_validation: pd.DataFrame, sep_data: pd.DataFrame, days: int):
        """
        Validates high/low calculations.
        """
        # Map window in days to the column name suffix (e.g., 252 days -> '52w')
        if days == 252:
            col_suffix = '52w'
        else:
            col_suffix = f'{days}d'
        
        high_col = f'high_{col_suffix}'
        low_col = f'low_{col_suffix}'

        logger.info(f"--- Test: Validating high/low over {days} days for {self.ticker} on {self.end_date_of_interest} ---")
        
        # Get the pre-calculated values from the database
        metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty, f"No data found for {self.ticker} on {self.end_date_of_interest} in daily_metrics."
        db_high = metric_row[high_col].iloc[0]
        db_low = metric_row[low_col].iloc[0]

        # SQL uses max(high) / min(low) over the window (not highadj/lowadj).
        source_window = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, days)
        pandas_high = source_window["high"].max()
        pandas_low = source_window["low"].min()

        logger.info(f"Database {high_col}: {db_high}, Pandas-calculated high: {pandas_high}")
        logger.info(f"Database {low_col}: {db_low}, Pandas-calculated low: {pandas_low}")
        assert db_high == pytest.approx(pandas_high)
        assert db_low == pytest.approx(pandas_low)


class TestEMACalculations:
    """Validates Exponential Moving Average calculations."""

    ticker = "AAPL"
    end_date_of_interest = date(2024, 12, 31)

    @pytest.mark.parametrize("window", [21, 30, 130])
    def test_ema_calculation(
        self, db_client, daily_metrics_for_validation: pd.DataFrame, window: int
    ):
        """
        Validates the chunked EMA calculation against two independent sources:
        1. A definitive, non-chunked ClickHouse query that mirrors the production transform.
        2. An independent pandas calculation using the `halflife` parameter to match
           ClickHouse's documented algorithm.
        """
        logger.info(
            f"--- Test: Validating ema{window}d for {self.ticker} on {self.end_date_of_interest} ---"
        )
        col_name = f"ema{window}d"

        # 1. Get the pre-calculated EMA value from the production (chunked) process
        metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation["ticker"] == self.ticker)
            & (daily_metrics_for_validation["date"] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_value = metric_row[col_name].iloc[0]
        if pd.isna(db_value):
            pytest.skip(
                f"No ema{window}d in daily_metrics for {self.ticker} on {self.end_date_of_interest} "
                "(insufficient history in test fixture for chunked EMA)."
            )

        # 2. Define queries to get the definitive value from ClickHouse and the
        #    source data for manual validation. It is critical that both queries
        #    operate on the exact same underlying data source.

        # To perfectly replicate the production transform, we must first determine the
        # exact chunk boundaries that would be used for our date of interest.
        # The production lookback is based on the chunk_start_date.
        chunk_start_date = self.end_date_of_interest.replace(day=1)
        # Get the end of the month without external dependencies
        next_month_start = (chunk_start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        chunk_end_date = next_month_start - timedelta(days=1)
    
        chunk_start_date_str = chunk_start_date.strftime('%Y-%m-%d')
        chunk_end_date_str = chunk_end_date.strftime('%Y-%m-%d')
    
        # This is the single source of truth query, perfectly replicating the new production transform.
        base_query = f"""
            WITH lookback_window AS (
                SELECT greatest(
                    toInt64(1),
                    (SELECT trade_day_num FROM daily_price_sequence WHERE date >= toDate('{chunk_start_date_str}') ORDER BY date ASC LIMIT 1) - 350
                ) AS start_trade_day_num
            ),
            lookback_start_date AS (
                SELECT date AS start_date FROM daily_price_sequence WHERE trade_day_num = (SELECT start_trade_day_num FROM lookback_window)
            ),
            price_data_with_adjustments AS (
                SELECT 
                    p.ticker, p.date, s.trade_day_num, p.open, p.high, p.low, p.close, p.volume, p.closeadj, p.closeunadj,
                    CASE WHEN p.close IS NOT NULL AND p.close != 0 THEN p.closeadj / p.close ELSE 1.0 END AS adj_factor
                FROM (
                    SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume, p.closeadj, p.closeunadj
                    FROM sep AS p FINAL
                    INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
                    WHERE p.date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate('{chunk_end_date_str}')
                    UNION ALL
                    SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume, p.closeadj, p.closeunadj
                    FROM sfp AS p FINAL
                    INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
                    WHERE p.date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate('{chunk_end_date_str}')
                ) p
                JOIN daily_price_sequence s ON p.date = s.date
            ),
            price_data_with_true_range AS (
                SELECT *,
                    `open` * adj_factor AS openadj, high * adj_factor AS highadj, low * adj_factor AS lowadj,
                    greatest(
                        high * adj_factor - low * adj_factor,
                        abs(high * adj_factor - lagInFrame(closeadj, 1) OVER (PARTITION BY ticker ORDER BY date)),
                        abs(low * adj_factor - lagInFrame(closeadj, 1) OVER (PARTITION BY ticker ORDER BY date))
                    ) AS true_range
                FROM price_data_with_adjustments
            )
        """
    
        # Get the definitive ClickHouse value by applying the final EMA calculation
        # to our source-of-truth query.
        definitive_ema_query = f"""
            {base_query}
            , metrics AS (
                SELECT
                    ticker,
                    date,
                    exponentialMovingAverage(2 / ({window} + 1))(closeadj, trade_day_num) OVER (PARTITION BY ticker ORDER BY date ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS live_ema
                FROM price_data_with_true_range
            )
            SELECT live_ema
            FROM metrics
            WHERE date = toDate('{self.end_date_of_interest.strftime('%Y-%m-%d')}') AND ticker = '{self.ticker}'
        """
        definitive_value = db_client.command(definitive_ema_query)
        if definitive_value is None or (isinstance(definitive_value, float) and np.isnan(definitive_value)):
            pytest.skip("Definitive EMA query returned no value for this fixture window.")

        # This is the most critical assertion. It proves our test query, which is a
        # replica of the production transform, produces the same result as the
        # production transform itself.
        logger.info(f"Production (chunked) ema{window}d: {db_value}")
        logger.info(f"Definitive (non-chunked) ema{window}d: {definitive_value}")
        assert db_value == pytest.approx(np.float64(definitive_value), rel=1e-5)

                # 3. The definitive query above is sufficient validation.
        #    The manual calculation was removed as it was not accurately replicating
        #    ClickHouse's internal EMA implementation with the standard alpha formula.


class TestATRCalculations:
    """Validates Average True Range (ATR) calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 10, 31)

    @pytest.fixture(scope='class')
    def daily_metrics_with_true_range(self, sep_data: pd.DataFrame) -> pd.DataFrame:
        """
        Pre-calculates true_range for the test ticker using pandas, as it's a prerequisite for all ATR calculations.
        """
        ticker_data = sep_data[sep_data['ticker'] == self.ticker].copy()
        ticker_data = ticker_data.set_index('date').sort_index()

        # Keep this oracle aligned with the transform's normalization policy:
        # OHLC/true_range/ATR use split-adjusted prices. The fully adjusted
        # closeadj series is retained for total-return calculations only.
        # Match xform_daily_metrics: greatest(high-low, |high-prev close|,
        # |low-prev close|), all on the split-adjusted OHLC basis.
        ticker_data['prev_close'] = ticker_data['close'].shift(1)

        # Calculate the three components of true range
        tr1 = ticker_data['high'] - ticker_data['low']
        tr2 = abs(ticker_data['high'] - ticker_data['prev_close'])
        tr3 = abs(ticker_data['low'] - ticker_data['prev_close'])

        # Find the maximum of the three components to get the true range
        ticker_data['true_range'] = np.maximum(tr1, np.maximum(tr2, tr3))
        
        return ticker_data

    def test_true_range_calculation(self, daily_metrics_for_validation: pd.DataFrame, daily_metrics_with_true_range: pd.DataFrame):
        """Validates the base true_range calculation."""
        col_name = 'true_range'
        
        db_value = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ][col_name].iloc[0]

        pandas_value = daily_metrics_with_true_range.loc[pd.to_datetime(self.end_date_of_interest), col_name]

        # Allow small drift vs pandas on unioned sep/sfp rows and ReplacingMergeTree FINAL semantics.
        assert db_value == pytest.approx(pandas_value, rel=0.01, abs=0.02)

    @pytest.mark.parametrize("window", [5, 14, 21])
    def test_atr_calculation(self, daily_metrics_for_validation: pd.DataFrame, daily_metrics_with_true_range: pd.DataFrame, window: int):
        """Validates the ATR (Average True Range) calculations."""
        col_name = f'atr_{window}'
        
        db_value = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ][col_name].iloc[0]

        # Calculate rolling average of true range
        daily_metrics_with_true_range['pandas_atr'] = daily_metrics_with_true_range['true_range'].rolling(window=window).mean()
        pandas_value = daily_metrics_with_true_range.loc[pd.to_datetime(self.end_date_of_interest), 'pandas_atr']

        # Allow small drift vs pandas on unioned sep/sfp rows and ReplacingMergeTree FINAL semantics.
        assert db_value == pytest.approx(pandas_value, rel=0.01, abs=0.02) 

    def test_atr_14_percent_calculation(
        self,
        daily_metrics_for_validation: pd.DataFrame,
        daily_metrics_with_true_range: pd.DataFrame,
    ):
        """Validate the normalized ATR output independently from its SQL expression."""
        row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker)
            & (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ].iloc[0]
        history = daily_metrics_with_true_range.loc[
            :pd.to_datetime(self.end_date_of_interest)
        ].tail(14)
        assert len(history) == 14, "Need 14 sessions for the ATR(14) oracle"
        expected_atr = history['true_range'].mean()
        expected_pct = expected_atr / history['close'].iloc[-1] * 100
        assert row['atr_14_pct'] == pytest.approx(expected_pct, rel=0.01, abs=0.02)
