-- This table stores daily price data and calculated technical indicators for each stock.
-- Daily Technical Metrics Table
-- This table stores a wide range of daily technical indicators calculated primarily from price and volume data.
-- It includes various moving averages (SMA, EMA), 52-week high/low, average volumes, performance over different periods,
-- and Volatility Contraction Pattern (VCP) metrics. Data is sourced and calculated by the transform defined below.
CREATE TABLE IF NOT EXISTS daily_metrics
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'Trading date',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update to this record',
    `open` Nullable(Float64) COMMENT 'Open Price - Split Adjusted (from sep.open and sfp.open)',
    `high` Nullable(Float64) COMMENT 'High Price - Split Adjusted (from sep.high and sfp.high)',
    `low` Nullable(Float64) COMMENT 'Low Price - Split Adjusted (from sep.low and sfp.low)',
    `close` Nullable(Float64) COMMENT 'Close Price - Split Adjusted (from sep.close and sfp.close)',
    `volume` Nullable(Float64) COMMENT 'Volume - Split Adjusted (from sep.volume and sfp.volume)',
    `openadj` Nullable(Float64) COMMENT 'Open Price - Fully Adjusted (derived using closeadj/close ratio)',
    `highadj` Nullable(Float64) COMMENT 'High Price - Fully Adjusted (derived using closeadj/close ratio)',
    `lowadj` Nullable(Float64) COMMENT 'Low Price - Fully Adjusted (derived using closeadj/close ratio)',
    `closeadj` Nullable(Float64) COMMENT 'Close Price - Fully Adjusted (from sep.closeadj)',
    `sma10d` Nullable(Float64) COMMENT '10-day Simple Moving Average of split-adjusted close',
    `sma20d` Nullable(Float64) COMMENT '20-day Simple Moving Average of split-adjusted close',
    `sma50d` Nullable(Float64) COMMENT '50-day Simple Moving Average of split-adjusted close',
    `sma150d` Nullable(Float64) COMMENT '150-day Simple Moving Average of split-adjusted close',
    `sma200d` Nullable(Float64) COMMENT '200-day Simple Moving Average of split-adjusted close',
    `ema21d` Nullable(Float64) COMMENT '21-day Exponential Moving Average of split-adjusted close',
    `ema30d` Nullable(Float64) COMMENT '30-day Exponential Moving Average of split-adjusted close',
    `ema130d` Nullable(Float64) COMMENT '130-day Exponential Moving Average of split-adjusted close',
    `high_5d` Nullable(Float64) COMMENT 'Highest high price over last 5 trading days',
    `high_30d` Nullable(Float64) COMMENT 'Highest high price over last 30 trading days',
    `high_90d` Nullable(Float64) COMMENT 'Highest high price over last 90 trading days',
    `high_52w` Nullable(Float64) COMMENT 'Highest high price over last 252 trading days',
    `low_5d` Nullable(Float64) COMMENT 'Lowest low price over last 5 trading days',
    `low_30d` Nullable(Float64) COMMENT 'Lowest low price over last 30 trading days',
    `low_90d` Nullable(Float64) COMMENT 'Lowest low price over last 90 trading days',
    `low_52w` Nullable(Float64) COMMENT 'Lowest low price over last 252 trading days',
    `avg_vol_5d` Nullable(Float64) COMMENT '5-day average volume',
    `avg_vol_20d` Nullable(Float64) COMMENT '20-day average volume',
    `avg_vol_30d` Nullable(Float64) COMMENT '30-day average volume',
    `avg_vol_50d` Nullable(Float64) COMMENT '50-day average volume',
    `avg_vol_60d` Nullable(Float64) COMMENT '60-day average volume',
    `avg_vol_90d` Nullable(Float64) COMMENT '90-day average volume',
    `true_range` Nullable(Float64) COMMENT 'True Range: max(high-low, |high-prev_close|, |low-prev_close|)',
    `atr_5` Nullable(Float64) COMMENT '5-day Average True Range: simple moving average of True Range for short-term volatility',
    `atr_14` Nullable(Float64) COMMENT '14-day Average True Range: simple moving average of True Range (not Wilder RMA)',
    `atr_21` Nullable(Float64) COMMENT '21-day Average True Range: simple moving average of True Range for monthly behavior',
    `atr_14_pct` Nullable(Float64) COMMENT 'ATR_14 as percentage of closing price (normalized volatility), based on SMA(TR)'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_metrics
-- Daily Technical Metrics Transform
-- This transform populates the daily_metrics table with daily technical indicators.
-- It calculates a variety of daily technical indicators and price/volume metrics
-- for each ticker, sourcing data from sigmarail.sep (equity prices) and sigmarail.sfp (fund prices).
-- It leverages window functions for moving averages, performance calculations, and VCP (Volatility Contraction Pattern) analysis.
--
-- NORMALIZATION POLICY (Option A):
--   - Store split-adjusted OHLCV in (open, high, low, close, volume).
--   - Compute technical indicators (SMAs, highs/lows, True Range, ATR) using split-adjusted prices.
--   - Retain fully-adjusted fields (closeadj and derived openadj/highadj/lowadj) for analytics/total-return views.
--
-- RATIONALE:
--   - Avoid dividend/spinoff adjustments distorting chart-based signals (breakouts/MAs/ATR) and keep
--     indicator semantics consistent with the stored OHLCV series used for backtesting and execution.
-- Expects ClickHouse parameters: chunk_start_date, chunk_end_date
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of daily metrics for tickers that haven't changed
--
DROP VIEW IF EXISTS xform_daily_metrics;

CREATE VIEW IF NOT EXISTS xform_daily_metrics (
    ticker,
    date,
    lastupdated,
    open,
    high,
    low,
    close,
    volume,
    openadj,
    highadj,
    lowadj,
    closeadj,
    sma10d,
    sma20d,
    sma50d,
    sma150d,
    sma200d,
    ema21d,
    ema30d,
    ema130d,
    high_5d,
    high_30d,
    high_90d,
    high_52w,
    low_5d,
    low_30d,
    low_90d,
    low_52w,
    avg_vol_5d,
    avg_vol_20d,
    avg_vol_30d,
    avg_vol_50d,
    avg_vol_60d,
    avg_vol_90d,
    true_range,
    atr_5,
    atr_14,
    atr_21,
    atr_14_pct
)
COMMENT '{"order":1,"target":"daily_metrics","sources":["sep","tickers","sfp","daily_price_sequence"],"chunk_size":"1w"}'
AS
-- This CTE is the core of the new, scalable lookback logic.
-- It uses the global daily_price_sequence to determine the exact start date
-- for a 350-trading-day lookback window.
WITH
-- Check freshness per ticker - only process tickers where source data is newer
ticker_freshness_check AS (
    SELECT
        dm.ticker,
        count() as target_row_count,
        max(dm.lastupdated) as target_last_updated
    FROM daily_metrics dm FINAL
    WHERE dm.date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String}
    GROUP BY dm.ticker
),
-- Get source freshness per ticker (routed by tickers.table — never merge SEP∪SFP on string alone)
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM (
        SELECT p.ticker, p.lastupdated
        FROM sep AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
        WHERE p.date BETWEEN {chunk_start_date:String} AND toDate({chunk_end_date:String})
        UNION ALL
        SELECT p.ticker, p.lastupdated
        FROM sfp AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
        WHERE p.date BETWEEN {chunk_start_date:String} AND toDate({chunk_end_date:String})
    ) s
    GROUP BY ticker
),
-- Determine which tickers need updating
-- {force_refresh:UInt8}=1 bypasses per-ticker freshness (needed after split rewrites:
-- max(lastupdated) over a chunk can hide stale dates for the same ticker).
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN {force_refresh:UInt8} = 1 THEN 1
            WHEN t.target_last_updated IS NULL THEN 1  -- New ticker
            WHEN s.source_row_count > t.target_row_count THEN 1  -- Missing rows in target for this chunk
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
),
lookback_window AS (
    SELECT
        -- Get the trade day number for the start of the current processing chunk.
        -- Clamp to >= 1: Sharadar EOD starts 1997-12-31 (trade_day_num=1); a raw
        -- (start - 350) before that returns no lookback row and early chunks insert 0.
        greatest(
            toInt64(1),
            (
                SELECT trade_day_num
                FROM daily_price_sequence FINAL
                WHERE date >= toDate({chunk_start_date:String})
                ORDER BY date ASC
                LIMIT 1
            ) - 350
        ) AS start_trade_day_num
),
-- Use the calculated start trade day number to find the actual calendar start date.
lookback_start_date AS (
    SELECT
        date AS start_date
    FROM daily_price_sequence FINAL
    WHERE trade_day_num = (SELECT start_trade_day_num FROM lookback_window)
    LIMIT 1
),
price_data_with_adjustments AS (
    SELECT
        p.ticker,
        p.date,
        s.trade_day_num,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        p.closeadj,
        p.closeunadj,
        CASE
            WHEN p.close IS NOT NULL AND p.close != 0
            THEN p.closeadj / p.close
            ELSE 1.0
        END AS adj_factor
    FROM (
        -- Route prices by tickers.table (Sharadar identity). Do not argMax across
        -- sep∪sfp on ticker string — recycled symbols (e.g. BNY bank vs CEF) are
        -- different issuers; fund history lives under successor keys (BNY1).
        SELECT
            p.ticker,
            p.date,
            p.open,
            p.high,
            p.low,
            p.close,
            p.volume,
            p.closeadj,
            p.closeunadj
        FROM sep AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
        WHERE p.date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
        UNION ALL
        SELECT
            p.ticker,
            p.date,
            p.open,
            p.high,
            p.low,
            p.close,
            p.volume,
            p.closeadj,
            p.closeunadj
        FROM sfp AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
        WHERE p.date BETWEEN (SELECT start_date FROM lookback_start_date) AND toDate({chunk_end_date:String})
    ) p
    -- Join with the global trade day sequence to get a stable timeunit for the EMA.
    JOIN daily_price_sequence s FINAL ON p.date = s.date
    -- NEW: Only process tickers that need updating
    WHERE p.ticker IN (
        SELECT ticker FROM tickers_needing_update WHERE needs_update = 1
    )
),
price_data_with_true_range AS (
    SELECT
        *,
        `open` * adj_factor AS openadj,
        high * adj_factor AS highadj,
        low * adj_factor AS lowadj,
        greatest(
            high - low,
            abs(high - lagInFrame(`close`, 1) OVER (PARTITION BY ticker ORDER BY date)),
            abs(low - lagInFrame(`close`, 1) OVER (PARTITION BY ticker ORDER BY date))
        ) AS true_range
    FROM price_data_with_adjustments
),
-- IMPORTANT: This CTE calculates metrics over the entire lookback window.
-- ClickHouse applies the 'WHERE' clause *before* calculating window functions.
-- Therefore, to get an accurate rolling calculation, we must compute it over
-- the full range of data first, before filtering down to the specific date chunk.
metrics_calculated_for_all_dates AS (
    SELECT
        -- Core Identifiers & Data
        ticker,
        date,
        now() AS lastupdated,

        -- Split-Adjusted Prices
        `open`,
        high,
        low,
        `close`,
        volume,

        -- Fully Adjusted Prices
        openadj,
        highadj,
        lowadj,
        closeadj,

        -- Daily Moving Averages
        avg(`close`) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS sma10d,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma20d,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50d,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS sma150d,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200d,

        -- Exponential Moving Averages
        -- NOTE: This implements a financial "trade day" EMA by using a pre-calculated, stable
        -- trade_day_num as the timeunit. This is the only way to ensure correctness
        -- with our chunked data processing architecture.
        CAST(NULL AS Nullable(Float64)) AS ema21d,
        CAST(NULL AS Nullable(Float64)) AS ema30d,
        CAST(NULL AS Nullable(Float64)) AS ema130d,

        -- Trend and Price Range Indicators
        max(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS high_5d,
        max(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS high_30d,
        max(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS high_90d,
        max(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,

        min(low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS low_5d,
        min(low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS low_30d,
        min(low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS low_90d,
        min(low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS low_52w,

        -- Average Volume Indicators
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS avg_vol_5d,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_vol_20d,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS avg_vol_30d,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS avg_vol_50d,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS avg_vol_60d,
        avg(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS avg_vol_90d,

        -- True Range and ATR Calculations
        true_range,
        avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS atr_5,
        avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS atr_14,
        avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS atr_21,
        (avg(true_range) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 AS atr_14_pct
    FROM price_data_with_true_range
)
SELECT
    *
FROM metrics_calculated_for_all_dates
WHERE date BETWEEN {chunk_start_date:String} AND {chunk_end_date:String};
