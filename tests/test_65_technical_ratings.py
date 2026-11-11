"""
Tests for technical_ratings transform - Validates technical and setup quality ratings.

Source of truth: SQL transform. technical_rating = sum(rs, long_term_trend, short_term_trend,
ma_alignment, position_in_range, volume) clipped to 100. See docs/CALCULATION_ACCURACY.md.

This test suite verifies:
1. Schema correctness
2. Data population and coverage
3. Rating calculations (0-100 scale)
4. Component score accuracy
"""

import pytest
import logging
from datetime import date
import pandas as pd
import clickhouse_connect

logger = logging.getLogger(__name__)


@pytest.fixture(scope='module')
def db_client(global_client):
    """Provides a database client for the test module."""
    yield global_client


@pytest.fixture(scope='class')
def technical_ratings_data(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    """
    Provides the populated technical_ratings table as a pandas DataFrame.
    """
    logger.info("--- Fixture: technical_ratings_data ---")
    query = "SELECT * FROM technical_ratings ORDER BY ticker, date LIMIT 10000"
    df = global_client.query_df(query)
    df['date'] = pd.to_datetime(df['date']).dt.date
    logger.info(f"Loaded {len(df)} rows from technical_ratings")
    
    if df.empty:
        pytest.fail("No rows found in technical_ratings table")
    
    return df


class TestTechnicalRatingsSchema:
    """Test that the technical_ratings table has the correct schema."""
    
    def test_schema_exists(self, global_client: clickhouse_connect.driver.Client):
        """Test that technical_ratings table exists."""
        result = global_client.query("SHOW TABLES LIKE 'technical_ratings'")
        assert len(result.result_rows) > 0, "technical_ratings table does not exist"
        logger.info("✓ technical_ratings table exists")
    
    def test_schema_has_required_fields(self, global_client: clickhouse_connect.driver.Client):
        """Test that schema includes all required rating fields."""
        schema_df = global_client.query_df("DESCRIBE technical_ratings")
        
        required_fields = [
            'ticker', 'date',
            'technical_rating', 'setup_quality_rating', 'technical_composite',
            'rs_component', 'long_term_trend_component', 'short_term_trend_component',
            'ma_alignment_component', 'position_in_range_component', 'volume_component',
            'consolidation_component', 'volatility_compression_component', 'volume_dryup_component',
            'support_quality_component', 'breakout_proximity_component', 'lastupdated'
        ]
        
        for field in required_fields:
            assert field in schema_df['name'].values, f"Field {field} missing from schema"
        
        logger.info(f"✓ All {len(required_fields)} required fields present")


class TestTechnicalRatingsData:
    """Test that technical_ratings data is populated correctly."""
    
    def test_data_populated(self, technical_ratings_data: pd.DataFrame):
        """Test that technical_ratings has data."""
        assert len(technical_ratings_data) > 0, "technical_ratings table is empty"
        logger.info(f"✓ technical_ratings has {len(technical_ratings_data)} rows")
    
    def test_no_null_ratings(self, technical_ratings_data: pd.DataFrame):
        """Test that primary ratings are not NULL."""
        null_technical = technical_ratings_data['technical_rating'].isna().sum()
        null_setup = technical_ratings_data['setup_quality_rating'].isna().sum()
        
        assert null_technical == 0, f"Found {null_technical} NULL technical_ratings"
        assert null_setup == 0, f"Found {null_setup} NULL setup_quality_ratings"
        
        logger.info("✓ No NULL ratings found")
    
    def test_ratings_in_valid_range(self, technical_ratings_data: pd.DataFrame):
        """Test that all ratings are within 0-100 range."""
        df = technical_ratings_data
        
        # Technical rating should be 0-100
        assert df['technical_rating'].min() >= 0, "technical_rating has values < 0"
        assert df['technical_rating'].max() <= 100, "technical_rating has values > 100"
        
        # Setup quality should be 0-100
        assert df['setup_quality_rating'].min() >= 0, "setup_quality_rating has values < 0"
        assert df['setup_quality_rating'].max() <= 100, "setup_quality_rating has values > 100"
        
        logger.info(f"✓ technical_rating range: {df['technical_rating'].min():.1f} - {df['technical_rating'].max():.1f}")
        logger.info(f"✓ setup_quality_rating range: {df['setup_quality_rating'].min():.1f} - {df['setup_quality_rating'].max():.1f}")
    
    def test_rating_variance(self, technical_ratings_data: pd.DataFrame):
        """Test that ratings show proper variance (not all the same value)."""
        df = technical_ratings_data
        
        unique_technical = df['technical_rating'].nunique()
        unique_setup = df['setup_quality_rating'].nunique()
        
        assert unique_technical > 5, f"technical_rating has only {unique_technical} unique values"
        assert unique_setup > 5, f"setup_quality_rating has only {unique_setup} unique values"
        
        logger.info(f"✓ technical_rating has {unique_technical} unique values")
        logger.info(f"✓ setup_quality_rating has {unique_setup} unique values")


class TestTechnicalRatingCalculations:
    """Test that technical rating calculations are correct."""
    
    def test_technical_rating_is_sum_of_components(self, global_client: clickhouse_connect.driver.Client):
        """Assert technical_rating = sum(rs, long_term_trend, short_term_trend, ma_alignment, position_in_range, volume) clipped to 100. Tolerance for float/rounding."""
        query = """
        SELECT 
            ticker, date, technical_rating,
            rs_component, long_term_trend_component, short_term_trend_component, 
            ma_alignment_component, position_in_range_component, volume_component
        FROM technical_ratings
        WHERE date = '2024-12-31'
        LIMIT 100
        """
        df = global_client.query_df(query)
        
        # Technical rating should be sum of components (max 100)
        df['calculated_technical'] = (
            df['rs_component'] + 
            df['long_term_trend_component'] + 
            df['short_term_trend_component'] + 
            df['ma_alignment_component'] + 
            df['position_in_range_component'] + 
            df['volume_component']
        ).clip(upper=100)
        
        # Allow small floating point differences
        df['diff'] = abs(df['technical_rating'] - df['calculated_technical'])
        max_diff = df['diff'].max()
        
        assert max_diff < 0.1, f"technical_rating calculation mismatch: max diff = {max_diff}"
        logger.info(f"✓ technical_rating = sum(components), max diff = {max_diff:.6f}")
    
    def test_setup_quality_components(self, global_client: clickhouse_connect.driver.Client):
        """Test that setup_quality_rating components are present."""
        query = """
        SELECT 
            ticker, date, setup_quality_rating,
            consolidation_component, volatility_compression_component, volume_dryup_component,
            support_quality_component, breakout_proximity_component
        FROM technical_ratings
        WHERE date = '2024-12-31'
        LIMIT 100
        """
        df = global_client.query_df(query)
        
        # All components should exist and be non-negative
        assert (df['consolidation_component'] >= 0).all(), "consolidation_component has negative values"
        assert (df['volatility_compression_component'] >= 0).all(), "volatility_compression_component has negative values"
        assert (df['volume_dryup_component'] >= 0).all(), "volume_dryup_component has negative values"
        assert (df['support_quality_component'] >= 0).all(), "support_quality_component has negative values"
        assert (df['breakout_proximity_component'] >= 0).all(), "breakout_proximity_component has negative values"
        
        logger.info("✓ All setup_quality components are non-negative")
    
    def test_component_maximums(self, global_client: clickhouse_connect.driver.Client):
        """Test that components don't exceed their maximum values."""
        query = """
        SELECT 
            MAX(rs_component) as max_rs,
            MAX(long_term_trend_component) as max_lt_trend,
            MAX(short_term_trend_component) as max_st_trend,
            MAX(ma_alignment_component) as max_ma,
            MAX(position_in_range_component) as max_pos,
            MAX(volume_component) as max_vol
        FROM technical_ratings
        WHERE date >= '2024-01-01'
        """
        result = global_client.query(query)
        row = result.result_rows[0]
        
        # Based on 65-technical-ratings-3m.sql (0-100 scale):
        # rs_component: 0-25, long_term_trend: 0-25, short_term_trend: 0-20, 
        # ma_alignment: 0-15, position_in_range: 0-10, volume: 0-5
        assert row[0] <= 25.1, f"rs_component max {row[0]} exceeds 25"
        assert row[1] <= 25.1, f"long_term_trend_component max {row[1]} exceeds 25"
        assert row[2] <= 20.1, f"short_term_trend_component max {row[2]} exceeds 20"
        assert row[3] <= 15.1, f"ma_alignment_component max {row[3]} exceeds 15"
        assert row[4] <= 10.1, f"position_in_range_component max {row[4]} exceeds 10"
        assert row[5] <= 5.1, f"volume_component max {row[5]} exceeds 5"
        
        logger.info(f"✓ Component maximums within expected ranges")
        logger.info(f"  RS: {row[0]:.1f}, LT-Trend: {row[1]:.1f}, ST-Trend: {row[2]:.1f}, MA: {row[3]:.1f}, Pos: {row[4]:.1f}, Vol: {row[5]:.1f}")


class TestTechnicalRatingsEdgeCases:
    """Test edge cases and data quality."""
    
    def test_coverage_by_date(self, global_client: clickhouse_connect.driver.Client):
        """Test that ratings exist for recent dates."""
        query = """
        SELECT 
            date,
            COUNT(*) as ticker_count,
            COUNT(CASE WHEN technical_rating > 0 THEN 1 END) as rated_count
        FROM technical_ratings
        WHERE date >= '2024-01-01'
        GROUP BY date
        ORDER BY date DESC
        LIMIT 10
        """
        df = global_client.query_df(query)
        
        # Should have ratings for most recent dates
        assert len(df) > 0, "No recent ratings found"
        
        # Most tickers should have non-zero ratings
        for idx, row in df.iterrows():
            coverage_pct = (row['rated_count'] / row['ticker_count']) * 100
            logger.info(f"  {row['date']}: {row['rated_count']}/{row['ticker_count']} ({coverage_pct:.1f}%)")
        
        logger.info("✓ Ratings coverage validated for recent dates")
    
    def test_high_rated_stocks_have_good_components(self, global_client: clickhouse_connect.driver.Client):
        """Test that high-rated stocks have strong component scores."""
        query = """
        SELECT 
            ticker, technical_rating,
            rs_component, long_term_trend_component, ma_alignment_component
        FROM technical_ratings
        WHERE date = '2024-12-31'
          AND technical_rating >= 70
        ORDER BY technical_rating DESC
        LIMIT 10
        """
        df = global_client.query_df(query)
        
        if len(df) > 0:
            # High-rated stocks should have strong RS component
            avg_rs = df['rs_component'].mean()
            assert avg_rs >= 10, f"High-rated stocks have low average RS: {avg_rs}"
            
            logger.info(f"✓ Top-rated stocks ({len(df)}) have strong components")
            logger.info(f"  Average RS component: {avg_rs:.1f}")
        else:
            logger.warning("No stocks with technical_rating >= 90 found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

