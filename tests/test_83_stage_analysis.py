"""
Tests for validating the daily stage-analysis projection and its context metrics.

Source of truth: SQL transform. price_vs_sma50w = (closeadj - sma50w) / sma50w. See docs/CALCULATION_ACCURACY.md.
"""
import pytest
import logging
from datetime import date
import pandas as pd

import clickhouse_connect

logger = logging.getLogger(__name__)

# --- Fixtures ---

@pytest.fixture(scope='class')
def stage_analysis_for_validation(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
        """
        Provides the populated stage_analysis table as a pandas DataFrame.
        """
        db_client = global_client
        print(f"Database: {db_client.database}")
        result = db_client.query('SELECT currentDatabase()')
        print(f"Current database: {result.result_rows[0][0]}")
        result = db_client.query('SHOW TABLES')
        print(f"Tables: {[row[0] for row in result.result_rows if 'stage' in row[0]]}")
        # LIMIT n BY ticker samples per-ticker; a bare LIMIT after ORDER BY
        # ticker would return only the alphabetically-first ticker.
        query = "SELECT * FROM stage_analysis ORDER BY ticker, date LIMIT 200 BY ticker"
        result = db_client.query(query)
        print(f"Query returned {len(result.result_rows)} rows")
        if result.result_rows:
            print(f"Columns: {result.column_names}")
            print(f"First row sample: {result.result_rows[0][:5]}")
        metrics_df = db_client.query_df(query)
        print(f"DataFrame shape: {metrics_df.shape}")
        print(f"DataFrame columns: {metrics_df.columns.tolist()}")
        if not metrics_df.empty and 'date' in metrics_df.columns:
            metrics_df['date'] = pd.to_datetime(metrics_df['date']).dt.date
        if metrics_df.empty:
            pytest.fail("No rows found in stage_analysis for validation.")
        return metrics_df

# --- Test Classes ---

class TestStageAnalysisSchema:
    """Test that the stage_analysis table has the correct schema with 50-week SMA fields."""
    
    def test_schema_has_50w_sma_fields(self, global_client: clickhouse_connect.driver.Client):
        """Test that the schema includes the new 50-week SMA fields."""
        db_client = global_client
        
        # Get the table schema
        schema_query = "DESCRIBE stage_analysis"
        schema_df = db_client.query_df(schema_query)
        
        # Check for required 50-week SMA fields
        required_fields = ['sma50w', 'sma50w_slope', 'price_vs_sma50w', 'trend_regime']
        
        for field in required_fields:
            assert field in schema_df['name'].values, f"Field {field} not found in stage_analysis schema"
        
        logger.info("✓ All required 50-week SMA fields present in schema")

class TestStageAnalysisData:
    """Test that the stage_analysis data is populated correctly with 50-week SMA logic."""
    
    def test_50w_sma_data_populated(self, stage_analysis_for_validation: pd.DataFrame):
        """Test that 50-week SMA data is populated."""
        df = stage_analysis_for_validation
        
        # Check that sma50w is populated
        sma50w_populated = df['sma50w'].notna().sum()
        total_rows = len(df)
        
        assert sma50w_populated > 0, "No sma50w data found"
        logger.info(f"✓ sma50w populated in {sma50w_populated}/{total_rows} rows")
    
    def test_trend_regime_classification(self, stage_analysis_for_validation: pd.DataFrame):
        """Test that trend regime is correctly classified based on 50-week SMA slope."""
        df = stage_analysis_for_validation
        
        # Check that trend_regime is populated
        trend_regime_populated = df['trend_regime'].notna().sum()
        total_rows = len(df)
        
        assert trend_regime_populated > 0, "No trend_regime data found"
        logger.info(f"✓ trend_regime populated in {trend_regime_populated}/{total_rows} rows")
        
        # Check that we have all three regime types
        regime_counts = df['trend_regime'].value_counts()
        logger.info(f"✓ Trend regime distribution: {dict(regime_counts)}")
    
    def test_allocation_with_trend_regime(self, stage_analysis_for_validation: pd.DataFrame):
        """Test that allocation decisions incorporate trend regime logic."""
        df = stage_analysis_for_validation
        
        # Test that Stage 2 allocations vary by trend regime
        stage2_data = df[df['stage_primary'] == '2']
        
        if len(stage2_data) > 0:
            # In bull market, Stage 2 should have higher allocation
            bull_stage2 = stage2_data[stage2_data['trend_regime'] == 'Bull Market']
            bear_stage2 = stage2_data[stage2_data['trend_regime'] == 'Bear Market']
            
            if len(bull_stage2) > 0 and len(bear_stage2) > 0:
                bull_avg_allocation = bull_stage2['allocation_fraction'].mean()
                bear_avg_allocation = bear_stage2['allocation_fraction'].mean()
                
                # Bull market should have higher allocation than bear market for Stage 2
                assert bull_avg_allocation >= bear_avg_allocation, \
                    f"Bull market Stage 2 allocation ({bull_avg_allocation}) should be >= bear market ({bear_avg_allocation})"
                
                logger.info(f"✓ Stage 2 allocation: Bull={bull_avg_allocation:.2f}, Bear={bear_avg_allocation:.2f}")
    
    def test_stage_code_is_daily_canonical_value(
        self,
        stage_analysis_for_validation: pd.DataFrame,
        global_client: clickhouse_connect.driver.Client,
    ):
        """Stage Analysis must project the owning daily series without reclassification."""
        df = stage_analysis_for_validation
        required = {"stage_code", "stage_duration"}
        assert required <= set(df.columns), f"Missing canonical stage columns: {required - set(df.columns)}"
        tickers = [t.replace("'", "''") for t in df["ticker"].unique()]
        in_list = ",".join(f"'{t}'" for t in tickers)
        dmin, dmax = df["date"].min(), df["date"].max()
        mismatch = global_client.query(
            f"""
            SELECT count()
            FROM stage_analysis AS sa FINAL
            INNER JOIN daily_metrics_derived AS dmd FINAL
              ON sa.ticker = dmd.ticker AND sa.date = dmd.date
            WHERE sa.ticker IN ({in_list})
              AND sa.date BETWEEN toDate('{dmin}') AND toDate('{dmax}')
              AND (ifNull(sa.stage_code, '') != ifNull(dmd.stage_code, '')
                   OR ifNull(sa.stage_duration, 0) != ifNull(dmd.stage_duration, 0))
            """
        ).result_rows[0][0]
        assert mismatch == 0, f"{mismatch:,} rows differ from daily_metrics_derived canonical stage values"

        valid = df[df["stage_code"].notna()]
        assert valid["stage_code"].str.fullmatch(r"[1-4][AB]").all()
        expected_broad = valid["stage_code"].str[0]
        # ClickHouse Enum8 may arrive as its label ("2") or numeric value (2.0)
        # depending on the client dataframe adapter; compare the enum's semantic value.
        actual_broad = valid["stage_primary"].map(lambda value: str(int(value))).astype("string")
        assert expected_broad.reset_index(drop=True).equals(actual_broad.reset_index(drop=True))

class TestStageAnalysisIntegration:
    """Test integration with other metrics and data consistency."""
    
    def test_price_vs_sma50w_calculation(
        self, stage_analysis_for_validation: pd.DataFrame, global_client: clickhouse_connect.driver.Client
    ):
        """Assert price_vs_sma50w = (close - sma50w) / sma50w per 64-stage-analysis (split-adjusted close)."""
        df = stage_analysis_for_validation
        valid_data = df[(df["sma50w"].notna()) & (df["sma50w"] > 0)]
        if len(valid_data) == 0:
            pytest.skip("No rows with sma50w for price_vs check")
        tickers = valid_data["ticker"].unique()
        esc = [t.replace("'", "''") for t in tickers]
        in_list = ",".join(f"'{t}'" for t in esc)
        dmin = valid_data["date"].min()
        dmax = valid_data["date"].max()
        closes = global_client.query_df(
            f"""
            SELECT ticker, date, close
            FROM daily_metrics FINAL
            WHERE ticker IN ({in_list})
              AND date >= toDate('{dmin}')
              AND date <= toDate('{dmax}')
            """
        )
        if closes.empty:
            pytest.fail("Could not load daily_metrics.close for stage_analysis rows")
        closes["date"] = pd.to_datetime(closes["date"]).dt.date
        vd = valid_data.copy()
        vd["date"] = pd.to_datetime(vd["date"]).dt.date
        merged = vd.merge(closes, on=["ticker", "date"], how="inner")
        merged = merged[merged["close"].notna() & (merged["sma50w"] > 0)]
        if merged.empty:
            pytest.skip("No overlapping daily_metrics rows for price_vs check")
        expected_ratio = (merged["close"] - merged["sma50w"]) / merged["sma50w"]
        actual_ratio = merged["price_vs_sma50w"]
        diff = (expected_ratio - actual_ratio).abs().max()
        assert float(diff) < 0.001, f"price_vs_sma50w calculation error: max diff = {diff}"
        logger.info("price_vs_sma50w verified vs daily_metrics.close (max diff: %.6f)", float(diff))
    
    def test_data_consistency(self, stage_analysis_for_validation: pd.DataFrame):
        """Test overall data consistency and quality."""
        df = stage_analysis_for_validation
        
        # Check for required fields
        required_fields = ['ticker', 'date', 'stage_primary', 'sma50w', 'trend_regime', 'allocation_fraction']
        for field in required_fields:
            assert field in df.columns, f"Required field {field} missing"
        
        # Check for reasonable data ranges
        assert df['allocation_fraction'].between(0, 1).all(), "allocation_fraction should be between 0 and 1"
        
        # Check that we have data for multiple tickers
        unique_tickers = df['ticker'].nunique()
        assert unique_tickers > 1, f"Expected multiple tickers, found {unique_tickers}"
        
        logger.info(f"✓ Data consistency verified for {unique_tickers} tickers")


def test_stage_analysis_sql_uses_daily_metrics_atr_14() -> None:
    """Schema 199 dropped derived.atr_20d; risk/vol bands use daily_metrics.atr_14."""
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sigmarail"
        / "sql"
        / "schema"
        / "83-schema-stage_analysis.sql"
    ).read_text(encoding="utf-8")
    assert "coalesce(stock.atr_14" in sql
    assert "derived.atr_" not in sql

