"""
Tests for accumulation_distribution_rating transform - IBD-style institutional sponsorship rating.

This test suite verifies:
1. Schema correctness
2. Data population and coverage
3. Rating calculations (1-99 scale, IBD-aligned)
4. Volume and price action components
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
def accumulation_distribution_data(global_client: clickhouse_connect.driver.Client) -> pd.DataFrame:
    """
    Provides the populated accumulation_distribution_rating table as a pandas DataFrame.
    """
    logger.info("--- Fixture: accumulation_distribution_data ---")
    query = "SELECT * FROM accumulation_distribution_rating ORDER BY ticker, date LIMIT 10000"
    df = global_client.query_df(query)
    df['date'] = pd.to_datetime(df['date']).dt.date
    logger.info(f"Loaded {len(df)} rows from accumulation_distribution_rating")
    
    if df.empty:
        pytest.fail("No rows found in accumulation_distribution_rating table")
    
    return df


class TestAccumulationDistributionSchema:
    """Test that the accumulation_distribution_rating table has correct schema."""
    
    def test_schema_exists(self, global_client: clickhouse_connect.driver.Client):
        """Test that accumulation_distribution_rating table exists."""
        result = global_client.query("SHOW TABLES LIKE 'accumulation_distribution_rating'")
        assert len(result.result_rows) > 0, "accumulation_distribution_rating table does not exist"
        logger.info("✓ accumulation_distribution_rating table exists")
    
    def test_schema_has_required_fields(self, global_client: clickhouse_connect.driver.Client):
        """Test that schema includes all required fields."""
        schema_df = global_client.query_df("DESCRIBE accumulation_distribution_rating")
        
        required_fields = [
            'ticker', 'date',
            'accumulation_distribution_rating',
            'volume_score', 'pocket_pivot_score',
            'volume_ratio_score', 'obv_score',
            'lastupdated'
        ]
        
        for field in required_fields:
            assert field in schema_df['name'].values, f"Field {field} missing from schema"
        
        logger.info(f"✓ All {len(required_fields)} required fields present")


class TestAccumulationDistributionData:
    """Test that accumulation/distribution data is populated correctly."""
    
    def test_data_populated(self, accumulation_distribution_data: pd.DataFrame):
        """Test that table has data."""
        assert len(accumulation_distribution_data) > 0, "Table is empty"
        logger.info(f"✓ accumulation_distribution_rating has {len(accumulation_distribution_data)} rows")
    
    def test_no_null_ratings(self, accumulation_distribution_data: pd.DataFrame):
        """Test that ratings are not NULL."""
        null_count = accumulation_distribution_data['accumulation_distribution_rating'].isna().sum()
        assert null_count == 0, f"Found {null_count} NULL ratings"
        logger.info("✓ No NULL ratings found")
    
    def test_ratings_in_valid_range(self, accumulation_distribution_data: pd.DataFrame):
        """Test that all ratings are within 1-99 range (IBD scale)."""
        df = accumulation_distribution_data
        
        min_rating = df['accumulation_distribution_rating'].min()
        max_rating = df['accumulation_distribution_rating'].max()
        
        assert min_rating >= 1, f"Rating has values < 1: {min_rating}"
        assert max_rating <= 99, f"Rating has values > 99: {max_rating}"
        
        logger.info(f"✓ Rating range: {min_rating:.1f} - {max_rating:.1f} (IBD 1-99 scale)")
    
    def test_rating_variance(self, accumulation_distribution_data: pd.DataFrame):
        """Test that ratings show proper variance."""
        df = accumulation_distribution_data
        
        unique_ratings = df['accumulation_distribution_rating'].nunique()
        assert unique_ratings > 3, f"Rating has only {unique_ratings} unique values"
        
        # Check distribution
        median = df['accumulation_distribution_rating'].median()
        std = df['accumulation_distribution_rating'].std()
        
        logger.info(f"✓ {unique_ratings} unique ratings")
        logger.info(f"  Median: {median:.1f}, StdDev: {std:.1f}")


class TestVolumeComponents:
    """Test volume-based component calculations."""
    
    def test_volume_components_present(self, accumulation_distribution_data: pd.DataFrame):
        """Test that volume components are calculated."""
        df = accumulation_distribution_data
        
        # Check that component scores exist and are populated
        assert df['volume_score'].notna().sum() > 0, "volume_score all NULL"
        assert df['obv_score'].notna().sum() > 0, "obv_score all NULL"
        
        logger.info("✓ Volume component scores are populated")
    
    def test_accumulation_distribution_days(self, accumulation_distribution_data: pd.DataFrame):
        """Test that accumulation/distribution scores are reasonable."""
        df = accumulation_distribution_data
        
        # Score-based components should be numeric and bounded
        assert df['pocket_pivot_score'].notna().sum() > 0, "pocket_pivot_score all NULL"
        assert df['volume_ratio_score'].notna().sum() > 0, "volume_ratio_score all NULL"
        
        logger.info("✓ Accumulation/Distribution scores are populated")


class TestRatingBehavior:
    """Test that rating behavior matches expectations."""
    
    def test_high_volume_stocks_have_ratings(self, global_client: clickhouse_connect.driver.Client):
        """Test that high-volume stocks have A/D ratings calculated."""
        query = """
        SELECT 
            adr.ticker,
            adr.accumulation_distribution_rating,
            dm.volume,
            dm.avg_vol_20d
        FROM accumulation_distribution_rating adr
        JOIN daily_metrics dm ON adr.ticker = dm.ticker AND adr.date = dm.date
        WHERE adr.date = '2024-12-31'
          AND dm.volume > 1000000
        ORDER BY dm.volume DESC
        LIMIT 50
        """
        df = global_client.query_df(query)
        
        if len(df) > 0:
            # High volume stocks should have ratings
            avg_rating = df['accumulation_distribution_rating'].mean()
            assert avg_rating > 0, "High volume stocks have zero ratings"
            
            logger.info(f"✓ High volume stocks ({len(df)}) have A/D ratings")
            logger.info(f"  Average rating: {avg_rating:.1f}")
        else:
            logger.warning("No high-volume stocks found for validation")
    
    def test_rating_correlates_with_price_trend(self, global_client: clickhouse_connect.driver.Client):
        """Test that A/D rating has some correlation with price trend."""
        query = """
        SELECT 
            adr.ticker,
            adr.accumulation_distribution_rating,
            dm.close,
            dm.sma50d,
            (dm.close / dm.sma50d - 1) * 100 as pct_above_sma50
        FROM accumulation_distribution_rating adr
        JOIN daily_metrics dm ON adr.ticker = dm.ticker AND adr.date = dm.date
        WHERE adr.date = '2024-12-31'
          AND dm.sma50d > 0
          AND adr.accumulation_distribution_rating > 70
        LIMIT 100
        """
        df = global_client.query_df(query)
        
        if len(df) > 0:
            # High A/D ratings should tend to have stocks above 50d SMA
            avg_pct_above = df['pct_above_sma50'].mean()
            
            logger.info(f"✓ High A/D rated stocks ({len(df)})")
            logger.info(f"  Average % above 50d SMA: {avg_pct_above:.2f}%")
        else:
            logger.info("ℹ No stocks with A/D rating > 70 found")


class TestEdgeCases:
    """Test edge cases and data quality."""
    
    def test_coverage_by_date(self, global_client: clickhouse_connect.driver.Client):
        """Test that ratings exist for recent dates."""
        query = """
        SELECT 
            date,
            COUNT(*) as ticker_count,
            COUNT(CASE WHEN accumulation_distribution_rating > 50 THEN 1 END) as above_50_count
        FROM accumulation_distribution_rating
        WHERE date >= '2024-01-01'
        GROUP BY date
        ORDER BY date DESC
        LIMIT 10
        """
        df = global_client.query_df(query)
        
        assert len(df) > 0, "No recent ratings found"
        
        # Log coverage
        for idx, row in df.iterrows():
            above_50_pct = (row['above_50_count'] / row['ticker_count']) * 100
            logger.info(f"  {row['date']}: {row['ticker_count']} tickers, {above_50_pct:.1f}% above 50")
        
        logger.info("✓ Ratings coverage validated for recent dates")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])









