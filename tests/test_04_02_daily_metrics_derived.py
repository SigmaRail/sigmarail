"""
Tests for validating the contents of the daily_metrics_derived table.

Source of truth: pandas and documented formulas. DB validated against pandas for perf, ATR, etc. See docs/CALCULATION_ACCURACY.md.
"""
import pytest
import logging
import math
from datetime import date
import pandas as pd

import clickhouse_connect
from tests.test_04_01_daily_metrics import sep_data, get_metric_window, daily_metrics_for_validation

logger = logging.getLogger(__name__)

# --- Fixtures ---
@pytest.fixture(scope='class')
def daily_metrics_derived_for_validation(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    """
    Provides the populated daily_metrics_derived table as a pandas DataFrame.
    """
    db_client = global_client
    query = "SELECT * FROM daily_metrics_derived FINAL ORDER BY ticker, date"
    metrics_df = db_client.query_df(query)
    metrics_df['date'] = pd.to_datetime(metrics_df['date']).dt.date
    if metrics_df.empty:
        pytest.fail("No rows found in daily_metrics_derived for validation.")
    return metrics_df

# --- Test Classes ---

class TestPerformanceCalculations:
    """Validates performance calculations (total return)."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 20)  # Updated to match test data range

    @pytest.mark.parametrize("col, window", [
        ('perf_5d', 5), ('perf_10d', 10), ('perf_1m', 21),
        ('perf_3m', 63), ('perf_6m', 126), ('perf_1y', 252)
    ])
    def test_performance_calculation(self, sep_data, daily_metrics_derived_for_validation, col, window):
        """Test a specific performance calculation."""

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_perf = metric_row[col].iloc[0]

        # Re-calculate using pandas
        # For lagInFrame(closeadj, N), we need N+1 days (current day + N days back)
        pandas_data = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, window + 1)
        if len(pandas_data) < window + 1:
            pytest.skip(f"Not enough data for {col}. Found {len(pandas_data)} points, need {window + 1}.")

        # Derived transform uses lagInFrame(close, N) vs current close (split-adjusted close).
        current_price = pandas_data["close"].iloc[-1]
        price_ago = pandas_data["close"].iloc[0]
        pandas_perf = (current_price / price_ago) - 1 if price_ago else 0

        # Handle cases where longer-term performance calculations return NULL due to insufficient historical data
        if pd.isna(db_perf):
            if window > 100:  # For longer-term calculations (6m, 1y)
                logger.info(f"SKIP {col.upper()}: Insufficient historical data (window={window})")
                pytest.skip(f"Insufficient historical data for {col} (window={window})")
            else:
                assert db_perf == pytest.approx(pandas_perf, rel=1e-4), f"{col} mismatch: Pandas={pandas_perf}, DB={db_perf}"
        else:
            # For debugging, let's see what we're comparing
            logger.info(f"DEBUG {col.upper()}: DB={db_perf}, Pandas={pandas_perf}, Window={window}, Data points={len(pandas_data)}")
            assert db_perf == pytest.approx(pandas_perf, rel=1e-3), f"{col} mismatch: Pandas={pandas_perf}, DB={db_perf}"
        logger.info(f"PASS {col.upper()}: Value={db_perf}")

    @pytest.mark.parametrize("col, window", [
        ('total_return_5d', 5), ('total_return_10d', 10), ('total_return_1m', 21),
        ('total_return_3m', 63), ('total_return_6m', 126),
        ('total_return_9m', 189), ('total_return_1y', 252),
    ])
    def test_dividend_adjusted_total_return(self, sep_data, daily_metrics_derived_for_validation, col, window):
        """Total return uses the vendor's dividend-adjusted closeadj series."""
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker)
            & (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        history = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, window + 1)
        assert len(history) >= window + 1, f"Need {window + 1} sessions for {col} oracle"
        expected = history['closeadj'].iloc[-1] / history['closeadj'].iloc[0] - 1
        actual = metric_row[col].iloc[0]
        assert pd.notna(actual), f"{col} unexpectedly NULL with sufficient source history"
        assert actual == pytest.approx(expected, rel=1e-6, abs=1e-8)

    @pytest.mark.parametrize("col, start_lag, end_lag", [
        ('total_return_q1', 252, 189), ('total_return_q2', 189, 126),
        ('total_return_q3', 126, 63), ('total_return_q4', 63, 0),
    ])
    def test_dividend_adjusted_quarterly_return_segments(
        self, sep_data, daily_metrics_derived_for_validation, col, start_lag, end_lag
    ):
        """Quarter segments use adjusted closes at both segment boundaries."""
        row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker)
            & (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not row.empty
        history = get_metric_window(sep_data, self.ticker, self.end_date_of_interest, 253)
        assert len(history) >= 253, "Need a full 252-session history for quarter segmentation"
        start = history['closeadj'].iloc[-1 - start_lag]
        end = history['closeadj'].iloc[-1 - end_lag]
        expected = end / start - 1
        assert row[col].iloc[0] == pytest.approx(expected, rel=1e-6, abs=1e-8)

    def test_dividend_adjusted_quarters_compound_to_one_year(self, daily_metrics_derived_for_validation):
        """The four adjacent adjusted-price segments must compound to adjusted 1y return."""
        row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker)
            & (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not row.empty
        q_returns = [row[f'total_return_q{i}'].iloc[0] for i in range(1, 5)]
        one_year = row['total_return_1y'].iloc[0]
        assert all(pd.notna(value) for value in q_returns) and pd.notna(one_year)
        compounded = math.prod(1 + value for value in q_returns) - 1
        assert compounded == pytest.approx(one_year, rel=1e-9, abs=1e-10)

class TestSMATrendAndSlopeCalculations:
    """Validates SMA trend and slope calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    @pytest.mark.parametrize("window", [10, 20, 50, 150, 200])
    def test_sma_trend_calculation(self, daily_metrics_for_validation, daily_metrics_derived_for_validation, window):
        """Validates SMA trend calculations."""
        col_name = f'sma{window}d_trend'
        sma_col = f'sma{window}d'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_trend = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        close_px = source_metric_row["close"].iloc[0]
        sma_value = source_metric_row[sma_col].iloc[0]

        expected_trend = (close_px - sma_value) / sma_value if sma_value else 0

        assert db_trend == pytest.approx(expected_trend, rel=1e-3), f"{col_name} mismatch: Expected={expected_trend}, DB={db_trend}"
        logger.info(f"PASS {col_name.upper()}: Value={db_trend}")

    @pytest.mark.parametrize("window", [50, 200])
    def test_sma_slope_calculation(self, daily_metrics_for_validation, daily_metrics_derived_for_validation, window):
        """Validates SMA slope calculations."""
        if window == 50:
            slope_col_name = 'sma50d_slope_20d'
            lag_period = 20
        elif window == 200:
            slope_col_name = 'sma200d_slope_20d'
            lag_period = 20
        else:
            pytest.skip("No slope calculation for this SMA window.")

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_slope = metric_row[slope_col_name].iloc[0]

        sma_col_name = f'sma{window}d'

        # Get current and lagged SMA values
        current_metrics = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        current_sma = current_metrics[sma_col_name].iloc[0]

        # Precisely find the Nth prior trading day's data
        historical_data = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] < self.end_date_of_interest)
        ].sort_values(by='date', ascending=False)

        if len(historical_data) < lag_period:
            pytest.skip(f"Not enough historical data to calculate slope for {sma_col_name}")

        lagged_metrics = historical_data.iloc[lag_period - 1]
        lagged_sma = lagged_metrics[sma_col_name]

        expected_slope = (current_sma / lagged_sma) - 1 if lagged_sma else 0

        assert db_slope == pytest.approx(expected_slope, rel=1e-4), f"{slope_col_name} mismatch: Expected={expected_slope}, DB={db_slope}"
        logger.info(f"PASS {slope_col_name.upper()}: Value={db_slope}")


class TestDerivedATRCalculations:
    """Validates ATR-derived columns kept on daily_metrics_derived after migration 199.

    Raw ATR itself (atr_14/atr_14_pct) is validated against daily_metrics in
    test_04_01::TestATRCalculations; these three columns are composites.
    """
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def _ticker_history(self, daily_metrics_for_validation: pd.DataFrame) -> pd.DataFrame:
        hist = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] <= self.end_date_of_interest)
        ].sort_values(by='date')
        assert not hist.empty
        return hist

    def _derived_row(self, daily_metrics_derived_for_validation: pd.DataFrame) -> pd.Series:
        row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not row.empty
        return row.iloc[0]

    def test_atr_to_sma50(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """atr_to_sma50 = rolling-14 mean of true_range / sma50d * 100."""
        hist = self._ticker_history(daily_metrics_for_validation)
        db_value = self._derived_row(daily_metrics_derived_for_validation)['atr_to_sma50']

        prev_close = hist['close'].shift(1)
        true_range = pd.concat([
            hist['high'] - hist['low'],
            (hist['high'] - prev_close).abs(),
            (hist['low'] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr14 = true_range.rolling(window=14).mean().iloc[-1]
        sma50d = hist['sma50d'].iloc[-1]

        if pd.isna(db_value):
            pytest.skip("atr_to_sma50 NULL at test date")
        expected = atr14 / sma50d * 100 if sma50d else 0
        logger.info(f"DEBUG atr_to_sma50: DB={db_value}, Expected={expected}")
        assert db_value == pytest.approx(expected, rel=1e-4), f"atr_to_sma50 mismatch: Expected={expected}, DB={db_value}"
        logger.info(f"PASS ATR_TO_SMA50: Value={db_value}")

    def test_stage_slope30_atr(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """stage_slope30_atr = (sma150d - sma150d_lag_30d) / (atr_14 * sqrt(30))."""
        hist = self._ticker_history(daily_metrics_for_validation)
        db_value = self._derived_row(daily_metrics_derived_for_validation)['stage_slope30_atr']

        if len(hist) < 31:
            pytest.skip("Not enough history for sma150d lag-30")
        if pd.isna(db_value):
            pytest.skip("stage_slope30_atr NULL at test date")

        sma150_now = hist['sma150d'].iloc[-1]
        sma150_lag30 = hist['sma150d'].iloc[-31]
        atr_14 = hist['atr_14'].iloc[-1]

        denom = atr_14 * math.sqrt(30)
        expected = (sma150_now - sma150_lag30) / denom if denom else 0
        logger.info(f"DEBUG stage_slope30_atr: DB={db_value}, Expected={expected}")
        assert db_value == pytest.approx(expected, rel=1e-4), f"stage_slope30_atr mismatch: Expected={expected}, DB={db_value}"
        logger.info(f"PASS STAGE_SLOPE30_ATR: Value={db_value}")

    def test_vcp_atr_compression_5d_90d(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """vcp_atr_compression_5d_90d = (high_5d - low_5d) / (high_90d - low_90d)."""
        src = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not src.empty
        src = src.iloc[0]
        db_value = self._derived_row(daily_metrics_derived_for_validation)['vcp_atr_compression_5d_90d']

        if pd.isna(db_value):
            pytest.skip("vcp_atr_compression_5d_90d NULL at test date")
        denom = src['high_90d'] - src['low_90d']
        expected = (src['high_5d'] - src['low_5d']) / denom if denom else 0
        logger.info(f"DEBUG vcp_atr_compression_5d_90d: DB={db_value}, Expected={expected}")
        assert db_value == pytest.approx(expected, rel=1e-4), f"vcp_atr_compression_5d_90d mismatch: Expected={expected}, DB={db_value}"
        logger.info(f"PASS VCP_ATR_COMPRESSION_5D_90D: Value={db_value}")


class TestPriceRangeCalculations:
    """Validates price range calculations (52-week high/low)."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def test_price_to_52w_low_percentage(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """Test percentage distance from 52-week low."""
        col_name = 'price_to_52w_low_pct'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_pct = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        close_px = source_metric_row["close"].iloc[0]
        low_52w = source_metric_row['low_52w'].iloc[0]

        expected_pct = (close_px / low_52w) - 1 if low_52w else 0

        if pd.isna(db_pct):
            logger.info(f"SKIP {col_name.upper()}: Insufficient historical data")
            pytest.skip(f"Insufficient historical data for {col_name}")
        else:
            logger.info(f"DEBUG {col_name.upper()}: DB={db_pct}, Expected={expected_pct}")
            assert db_pct == pytest.approx(expected_pct, rel=1e-4), f"{col_name} mismatch: Expected={expected_pct}, DB={db_pct}"
        logger.info(f"PASS {col_name.upper()}: Value={db_pct}")

    def test_price_to_52w_high_percentage(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """Test percentage distance from 52-week high."""
        col_name = 'price_to_52w_high_pct'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_pct = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        close_px = source_metric_row["close"].iloc[0]
        high_52w = source_metric_row['high_52w'].iloc[0]

        expected_pct = (close_px / high_52w) - 1 if high_52w else 0

        if pd.isna(db_pct):
            logger.info(f"SKIP {col_name.upper()}: Insufficient historical data")
            pytest.skip(f"Insufficient historical data for {col_name}")
        else:
            logger.info(f"DEBUG {col_name.upper()}: DB={db_pct}, Expected={expected_pct}")
            assert db_pct == pytest.approx(expected_pct, rel=1e-4), f"{col_name} mismatch: Expected={expected_pct}, DB={db_pct}"
        logger.info(f"PASS {col_name.upper()}: Value={db_pct}")


class TestVCPCalculations:
    """Validates Volatility Contraction Pattern (VCP) calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def test_vcp_tightness_5d_90d(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """Test VCP tightness calculation."""
        col_name = 'vcp_tightness_5d_90d'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_tightness = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        high_5d = source_metric_row['high_5d'].iloc[0]
        low_5d = source_metric_row['low_5d'].iloc[0]
        high_90d = source_metric_row['high_90d'].iloc[0]

        expected_tightness = (high_5d - low_5d) / high_90d if high_90d else 0

        if pd.isna(db_tightness):
            logger.info(f"SKIP {col_name.upper()}: Insufficient historical data")
            pytest.skip(f"Insufficient historical data for {col_name}")
        else:
            logger.info(f"DEBUG {col_name.upper()}: DB={db_tightness}, Expected={expected_tightness}")
            assert db_tightness == pytest.approx(expected_tightness, rel=1e-4), f"{col_name} mismatch: Expected={expected_tightness}, DB={db_tightness}"
        logger.info(f"PASS {col_name.upper()}: Value={db_tightness}")

    def test_vcp_volume_dryup_5d_90d(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """Test VCP volume dry-up calculation."""
        col_name = 'vcp_volume_dryup_5d_90d'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_volume_ratio = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        avg_vol_5d = source_metric_row['avg_vol_5d'].iloc[0]
        avg_vol_90d = source_metric_row['avg_vol_90d'].iloc[0]

        expected_volume_ratio = avg_vol_5d / avg_vol_90d if avg_vol_90d else 0

        if pd.isna(db_volume_ratio):
            logger.info(f"SKIP {col_name.upper()}: Insufficient historical data")
            pytest.skip(f"Insufficient historical data for {col_name}")
        else:
            logger.info(f"DEBUG {col_name.upper()}: DB={db_volume_ratio}, Expected={expected_volume_ratio}")
            assert db_volume_ratio == pytest.approx(expected_volume_ratio, rel=1e-4), f"{col_name} mismatch: Expected={expected_volume_ratio}, DB={db_volume_ratio}"
        logger.info(f"PASS {col_name.upper()}: Value={db_volume_ratio}")

    def test_vcp_proximity_90d(self, daily_metrics_for_validation, daily_metrics_derived_for_validation):
        """Test VCP proximity to 90-day high."""
        col_name = 'vcp_proximity_90d'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_proximity = metric_row[col_name].iloc[0]

        # Re-calculate using source data
        source_metric_row = daily_metrics_for_validation[
            (daily_metrics_for_validation['ticker'] == self.ticker) &
            (daily_metrics_for_validation['date'] == self.end_date_of_interest)
        ]
        close_px = source_metric_row["close"].iloc[0]
        high_90d = source_metric_row['high_90d'].iloc[0]

        expected_proximity = close_px / high_90d if high_90d else 0

        if pd.isna(db_proximity):
            logger.info(f"SKIP {col_name.upper()}: Insufficient historical data")
            pytest.skip(f"Insufficient historical data for {col_name}")
        else:
            logger.info(f"DEBUG {col_name.upper()}: DB={db_proximity}, Expected={expected_proximity}")
            assert db_proximity == pytest.approx(expected_proximity, rel=1e-4), f"{col_name} mismatch: Expected={expected_proximity}, DB={db_proximity}"
        logger.info(f"PASS {col_name.upper()}: Value={db_proximity}")


class TestWeinsteinStageAnalysis:
    """Validates the canonical daily detailed stage series."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def test_weinstein_stage(self, daily_metrics_derived_for_validation):
        """The detailed token preserves both substage letters."""
        col_name = 'stage_code'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_stage = metric_row[col_name].iloc[0]

        if pd.isna(db_stage):
            logger.info(f"SKIP {col_name.upper()}: No stage data available")
            pytest.skip(f"No stage data available for {col_name}")
        else:
            assert db_stage in {'1A', '1B', '2A', '2B', '3A', '3B', '4A', '4B'}
            logger.info(f"PASS {col_name.upper()}: Stage={db_stage}")

    def test_weinstein_stage_duration(self, daily_metrics_derived_for_validation):
        """Duration counts consecutive observations of the detailed stage token."""
        col_name = 'stage_duration'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_duration = metric_row[col_name].iloc[0]

        # Validate that duration is a positive integer
        if pd.isna(db_duration):
            logger.info(f"SKIP {col_name.upper()}: No duration data available")
            pytest.skip(f"No duration data available for {col_name}")
        else:
            assert db_duration >= 1, f"{col_name} value {db_duration} should be positive"
            # Check if it's numeric (int or float) or if it can be converted to int
            try:
                int(db_duration)
                logger.info(f"PASS {col_name.upper()}: Duration={db_duration} (valid integer)")
            except (ValueError, TypeError):
                pytest.fail(f"{col_name} value {db_duration} should be convertible to integer")


class TestBreakoutSignals:
    """Validates breakout signal calculations."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def test_breakout_signal(self, daily_metrics_derived_for_validation):
        """Test breakout signal calculation."""
        col_name = 'breakout_signal'

        # Get the specific metric to test from the larger DataFrame
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty
        db_signal = metric_row[col_name].iloc[0]

        # Validate that signal is binary (0 or 1)
        if pd.isna(db_signal):
            logger.info(f"SKIP {col_name.upper()}: No signal data available")
            pytest.skip(f"No signal data available for {col_name}")
        else:
            assert db_signal in [0, 1], f"{col_name} value {db_signal} should be 0 or 1"
            logger.info(f"PASS {col_name.upper()}: Signal={db_signal}")


class TestDataQuality:
    """Validates overall data quality and consistency."""
    ticker = 'AAPL'
    end_date_of_interest = date(2024, 12, 30)

    def test_data_completeness(self, daily_metrics_derived_for_validation):
        """Test that all expected columns are present and have reasonable values."""
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty

        # Check that key columns exist
        expected_columns = [
            'ticker', 'date', 'lastupdated',
            'perf_5d', 'perf_10d', 'perf_1m', 'perf_3m', 'perf_6m', 'perf_1y',
            'total_return_5d', 'total_return_10d', 'total_return_1m', 'total_return_3m',
            'total_return_6m', 'total_return_9m', 'total_return_1y',
            'total_return_q1', 'total_return_q2', 'total_return_q3', 'total_return_q4',
            'sma10d_trend', 'sma20d_trend', 'sma50d_trend', 'sma150d_trend', 'sma200d_trend',
            'sma50d_slope_20d', 'sma200d_slope_20d',
            'price_to_52w_low_pct', 'price_to_52w_high_pct',
            'vcp_tightness_5d_90d', 'vcp_volume_dryup_5d_90d', 'vcp_proximity_90d',
            'stage_code', 'stage_duration', 'breakout_signal'
        ]

        for col in expected_columns:
            assert col in metric_row.columns, f"Expected column {col} not found in daily_metrics_derived"

        logger.info(f"PASS: All expected columns present in daily_metrics_derived")

    def test_value_ranges(self, daily_metrics_derived_for_validation):
        """Test that calculated values are within reasonable ranges."""
        metric_row = daily_metrics_derived_for_validation[
            (daily_metrics_derived_for_validation['ticker'] == self.ticker) &
            (daily_metrics_derived_for_validation['date'] == self.end_date_of_interest)
        ]
        assert not metric_row.empty

        # Test performance values are reasonable (not extreme)
        perf_columns = ['perf_5d', 'perf_10d', 'perf_1m', 'perf_3m', 'perf_6m', 'perf_1y']
        for col in perf_columns:
            if not pd.isna(metric_row[col].iloc[0]):
                value = metric_row[col].iloc[0]
                assert -0.5 <= value <= 2.0, f"{col} value {value} is outside reasonable range [-0.5, 2.0]"

        logger.info(f"PASS: All calculated values are within reasonable ranges")


def test_daily_derived_ratios_flags_and_risk_scores_match_python_oracle(
    daily_metrics_for_validation: pd.DataFrame,
    daily_metrics_derived_for_validation: pd.DataFrame,
):
    """Cross-check the straightforward derived SQL expressions as one contract.

    The reference is computed from the populated daily_metrics inputs with plain
    Python, rather than using the derived SQL outputs as expected values. Complex
    stage-state and VCP pivot logic has its own dedicated reference/contract tests.
    """
    ticker = "AAPL"
    as_of = date(2024, 12, 30)
    history = (
        daily_metrics_for_validation[
            (daily_metrics_for_validation["ticker"] == ticker)
            & (daily_metrics_for_validation["date"] <= as_of)
        ]
        .sort_values("date")
        .reset_index(drop=True)
    )
    assert len(history) >= 253, "Oracle requires a full 252-session lookback"
    source = history.iloc[-1]
    previous = history.iloc[-2]
    lag30 = history.iloc[-31]
    lag150 = history.iloc[-151]
    out = daily_metrics_derived_for_validation[
        (daily_metrics_derived_for_validation["ticker"] == ticker)
        & (daily_metrics_derived_for_validation["date"] == as_of)
    ]
    assert len(out) == 1, f"Expected one derived row for {ticker} on {as_of}"
    actual = out.iloc[0]

    close = float(source["close"])
    sma20, sma50 = float(source["sma20d"]), float(source["sma50d"])
    sma150, sma200 = float(source["sma150d"]), float(source["sma200d"])
    high52, low52 = float(source["high_52w"]), float(source["low_52w"])
    avg20, avg50 = float(source["avg_vol_20d"]), float(source["avg_vol_50d"])
    atr14 = float(source["atr_14"])

    expected = {
        "price_vs_sma20": close / sma20 * 100,
        "price_vs_sma50": close / sma50 * 100,
        "price_vs_sma150": close / sma150 * 100,
        "price_vs_sma200": close / sma200 * 100,
        "sma50_vs_sma150": sma50 / sma150 * 100,
        "sma150_vs_sma200": sma150 / sma200 * 100,
        "price_vs_52w_high": close / high52 * 100,
        "price_vs_52w_low": close / low52 * 100,
        "volume_sma20_vs_sma50": avg20 / avg50 * 100,
        "volume_trend_pct": (avg20 / avg50 - 1) * 100,
        "price_range_52w_pct": (high52 - low52) / close * 100,
        "price_to_52w_low_pct": close / low52 - 1,
        "price_to_52w_high_pct": close / high52 - 1,
        "sma200_lag_30d": float(lag30["sma200d"]),
        "sma200d_rising_30d": int(sma200 > float(lag30["sma200d"])),
        "sma200d_rising_150d": int(sma200 > float(lag150["sma200d"])),
        "sma20d_crossover_up": int(
            close > sma20 and float(previous["close"]) <= float(previous["sma20d"])
        ),
        "price_above_sma20d": int(close > sma20),
        "price_above_sma50d": int(close > sma50),
        "price_above_sma150d": int(close > sma150),
        "price_above_sma200d": int(close > sma200),
        "sma50d_above_sma150d": int(sma50 > sma150),
        "sma50d_above_sma200d": int(sma50 > sma200),
        "sma150d_above_sma200d": int(sma150 > sma200),
        "price_30pct_above_52w_low": int(close >= low52 * 1.30),
        "price_70pct_above_52w_low": int(close >= low52 * 1.70),
        "price_within_25pct_52w_high": int(close >= high52 * 0.75),
    }

    atr_pct = atr14 / close * 100
    expected["atr_to_sma50"] = atr14 / sma50 * 100
    expected["volatility_risk_pct"] = (
        0.9 if atr_pct > 5 else 0.7 if atr_pct > 3 else 0.5 if atr_pct > 2 else 0.3 if atr_pct > 1 else 0.1
    )
    volume = float(source["volume"])
    expected["liquidity_risk_pct"] = (
        0.9 if volume < avg20 * 0.5 else 0.7 if volume < avg20 * 0.7
        else 0.5 if volume < avg20 * 0.9 else 0.3 if volume < avg20 * 1.1 else 0.1
    )
    expected["sector_risk_pct"] = 0.2
    expected["fundamental_risk_pct"] = 0.2
    expected["technical_risk_pct"] = (
        0.8 if close < sma200 else 0.6 if close < sma150
        else 0.4 if close < sma50 else 0.2 if close < sma20 else 0.1
    )
    expected["independent_risk_score"] = sum(
        expected[name]
        for name in (
            "volatility_risk_pct", "liquidity_risk_pct", "sector_risk_pct",
            "technical_risk_pct", "fundamental_risk_pct",
        )
    ) / 5

    for column, value in expected.items():
        assert actual[column] == pytest.approx(value, rel=1e-5, abs=1e-8), (
            f"{column}: SQL={actual[column]!r}; Python reference={value!r}"
        )
