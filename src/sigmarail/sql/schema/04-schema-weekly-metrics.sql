-- Foundational Weekly Metrics Schema
-- This table stores core weekly price aggregations and simple moving averages.
CREATE TABLE IF NOT EXISTS weekly_metrics
(
    `ticker` String COMMENT 'Stock ticker symbol',
    `date` Date COMMENT 'The start date of the week (Monday)',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Timestamp of the last update',
    `open` Nullable(Float64) COMMENT 'Opening price for the week, unadjusted',
    `high` Nullable(Float64) COMMENT 'Highest price for the week, unadjusted',
    `low` Nullable(Float64) COMMENT 'Lowest price for the week, unadjusted',
    `close` Nullable(Float64) COMMENT 'Closing price for the week, unadjusted',
    `openadj` Nullable(Float64) COMMENT 'Opening price for the week, adjusted for splits and dividends',
    `highadj` Nullable(Float64) COMMENT 'Highest price for the week, adjusted for splits and dividends',
    `lowadj` Nullable(Float64) COMMENT 'Lowest price for the week, adjusted for splits and dividends',
    `closeadj` Nullable(Float64) COMMENT 'Closing price for the week, adjusted for splits and dividends',
    `volume` Nullable(Float64) COMMENT 'Total volume for the week',
    `sma10w` Nullable(Float64) COMMENT '10-week simple moving average of split-adjusted close',
    `sma20w` Nullable(Float64) COMMENT '20-week simple moving average of split-adjusted close',
    `sma30w` Nullable(Float64) COMMENT '30-week simple moving average of split-adjusted close',
    `sma40w` Nullable(Float64) COMMENT '40-week simple moving average of split-adjusted close',
    `sma50w` Nullable(Float64) COMMENT '50-week simple moving average of split-adjusted close',
    `ema12w` Nullable(Float64) COMMENT '12-week exponential moving average of split-adjusted close',
    `ema20w` Nullable(Float64) COMMENT '20-week exponential moving average of split-adjusted close',
    `ema26w` Nullable(Float64) COMMENT '26-week exponential moving average of split-adjusted close',
    `weekly_tr` Nullable(Float64) COMMENT 'Weekly True Range',
    `week_volume_sma50` Nullable(Float64) COMMENT '50-week simple moving average of volume',
    `high_4w` Nullable(Float64) COMMENT 'Highest high price over last 4 weeks',
    `high_13w` Nullable(Float64) COMMENT 'Highest high price over last 13 weeks (1 quarter)',
    `high_26w` Nullable(Float64) COMMENT 'Highest high price over last 26 weeks (6 months)',
    `high_52w` Nullable(Float64) COMMENT 'Highest high price over last 52 weeks (1 year)',
    `low_4w` Nullable(Float64) COMMENT 'Lowest low price over last 4 weeks',
    `low_13w` Nullable(Float64) COMMENT 'Lowest low price over last 13 weeks (1 quarter)',
    `low_26w` Nullable(Float64) COMMENT 'Lowest low price over last 26 weeks (6 months)',
    `low_52w` Nullable(Float64) COMMENT 'Lowest low price over last 52 weeks (1 year)',
    `avg_vol_4w` Nullable(Float64) COMMENT '4-week average trading volume',
    `avg_vol_10w` Nullable(Float64) COMMENT '10-week average trading volume',
    `avg_vol_30w` Nullable(Float64) COMMENT '30-week average trading volume',
    `atr_10w` Nullable(Float64) COMMENT '10-week Average True Range for intermediate volatility',
    `atr_20w` Nullable(Float64) COMMENT '20-week Average True Range for position sizing',
    `atr_10w_pct` Nullable(Float64) COMMENT 'ATR_10w as percentage of closing price (normalized weekly volatility)'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: weekly_metrics
-- Foundational Weekly Metrics Transform
-- Populates weekly_metrics with core aggregations and simple moving averages.
-- This serves as a stable base for all other derived weekly indicators.
-- Expects SQL variables: chunk_start_date, chunk_end_date
--
-- NORMALIZATION POLICY (Option A):
--   - Weekly technical indicators (SMAs/EMAs/TR/ATR%/rolling highs-lows) are computed from split-adjusted weekly OHLC.
--   - Fully-adjusted weekly OHLC (openadj/highadj/lowadj/closeadj) is retained for analytics/total-return views.
--
-- ENHANCED: Only processes tickers where source data is newer than target data
-- This prevents unnecessary recalculation of weekly metrics for tickers that haven't changed
--
-- CLOSED WEEKS ONLY: Rows are emitted only for ISO weeks whose Monday + 4 trading-day offset
-- is <= max(trading date) in daily_price_sequence. This avoids publishing a partial in-flight
-- week that would change every session (US equities: Mon+4 targets end-of-week bar).
--
DROP VIEW IF EXISTS xform_weekly_metrics;

CREATE VIEW IF NOT EXISTS xform_weekly_metrics (
    ticker,
    date,
    lastupdated,
    open,
    high,
    low,
    close,
    openadj,
    highadj,
    lowadj,
    closeadj,
    volume,
    sma10w,
    sma20w,
    sma30w,
    sma40w,
    sma50w,
    ema12w,
    ema20w,
    ema26w,
    weekly_tr,
    week_volume_sma50,
    high_4w,
    high_13w,
    high_26w,
    high_52w,
    low_4w,
    low_13w,
    low_26w,
    low_52w,
    avg_vol_4w,
    avg_vol_10w,
    avg_vol_30w,
    atr_10w,
    atr_20w,
    atr_10w_pct
)
COMMENT '{"order":3,"target":"weekly_metrics","sources":["sep","tickers","sfp","daily_price_sequence"],"chunk_size":"12m"}'
AS
WITH
-- Check freshness per ticker - only process tickers where source data is newer
ticker_freshness_check AS (
    SELECT
        dm.ticker,
        count() as target_row_count,
        max(dm.lastupdated) as target_last_updated
    FROM weekly_metrics dm FINAL
    WHERE dm.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    GROUP BY dm.ticker
),
-- Get source freshness per ticker (routed by tickers.table)
source_freshness_check AS (
    SELECT
        ticker,
        count() as source_row_count,
        max(lastupdated) as source_last_updated
    FROM (
        SELECT p.ticker, p.lastupdated
        FROM sep AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
        WHERE p.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
        UNION ALL
        SELECT p.ticker, p.lastupdated
        FROM sfp AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
        WHERE p.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    ) s
    GROUP BY ticker
),
-- Determine which tickers need updating
tickers_needing_update AS (
    SELECT
        COALESCE(s.ticker, t.ticker) as ticker,
        CASE
            WHEN t.target_last_updated IS NULL THEN 1  -- New ticker
            WHEN s.source_row_count > t.target_row_count THEN 1  -- Missing rows in target for this chunk
            WHEN s.source_last_updated > t.target_last_updated THEN 1  -- Source is newer
            ELSE 0  -- Target is up-to-date
        END as needs_update
    FROM source_freshness_check s
    FULL OUTER JOIN ticker_freshness_check t ON s.ticker = t.ticker
),
price_data_with_adjustments AS (
    SELECT
        p.ticker,
        p.date,
        p.closeadj,
        p.high * (p.closeadj / p.close) AS high_adj,
        p.low * (p.closeadj / p.close) AS low_adj,
        p.open * (p.closeadj / p.close) AS open_adj,
        p.volume,
        p.high,
        p.low,
        p.open,
        p.close
    FROM (
        -- Route by tickers.table (do not merge SEP and SFP on ticker string alone)
        SELECT
            p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume, p.closeadj
        FROM sep AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'stocks'
        WHERE p.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
        UNION ALL
        SELECT
            p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume, p.closeadj
        FROM sfp AS p FINAL
        INNER JOIN tickers AS t FINAL ON t.ticker = p.ticker AND t.`table` = 'funds'
        WHERE p.date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) - INTERVAL 400 DAY AND toMonday(CAST({chunk_end_date:String}, 'Date'))
    ) p
    -- NEW: Only process tickers that need updating
    JOIN tickers_needing_update t ON p.ticker = t.ticker
    WHERE t.needs_update = 1
),
weekly_aggregated AS (
    SELECT
        ticker,
        toMonday(date) AS week_start,

        -- For weekly OHLC, we want the open from the first day of the week and the close from the last.
        -- argMin gets the value from the row with the minimum date in the group (Monday's open).
        -- argMax gets the value from the row with the maximum date in the group (Friday's close).
        argMin(open_adj, date) AS openadj,
        max(high_adj) AS highadj,
        min(low_adj) AS lowadj,
        argMax(closeadj, date) AS closeadj,
        sum(volume) AS volume,
        argMin(open, date) AS open,
        max(high) AS high,
        min(low) AS low,
        argMax(close, date) AS close,
        -- Use week number based on earliest week from daily_price_sequence for consistent EMA calculation
        (toMonday(date) - (SELECT MIN(toMonday(date)) FROM daily_price_sequence)) / 7 + 1 AS week_num
    FROM price_data_with_adjustments
    GROUP BY ticker, toMonday(date)
),
weekly_with_prev_close AS (
    SELECT
        *,
        lagInFrame(`close`, 1) OVER (PARTITION BY ticker ORDER BY week_start) AS prev_week_close
    FROM weekly_aggregated
),
weekly_with_true_range AS (
    SELECT
        *,
        greatest(
            high - low,
            abs(high - prev_week_close),
            abs(low - prev_week_close)
        ) AS weekly_tr
    FROM weekly_with_prev_close
),
metrics_calculated_for_all_weeks AS (
    SELECT
        ticker,
        week_start AS date,
        now() AS lastupdated,
        open,
        high,
        low,
        close,
        openadj,
        highadj,
        lowadj,
        closeadj,
        volume,
        -- Simple Moving Averages
        avg(`close`) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS sma10w,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma20w,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS sma30w,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 39 PRECEDING AND CURRENT ROW) AS sma40w,
        avg(`close`) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50w,
        -- Exponential Moving Averages
        exponentialMovingAverage(2 / (12 + 1))(`close`, week_num) OVER (PARTITION BY ticker ORDER BY week_start ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ema12w,
        exponentialMovingAverage(2 / (20 + 1))(`close`, week_num) OVER (PARTITION BY ticker ORDER BY week_start ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ema20w,
        exponentialMovingAverage(2 / (26 + 1))(`close`, week_num) OVER (PARTITION BY ticker ORDER BY week_start ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ema26w,
        -- Weekly True Range
        weekly_tr,
        -- Volume SMA
        avg(volume) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS week_volume_sma50,
        -- Weekly High Price Range Indicators
        max(high) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS high_4w,
        max(high) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 12 PRECEDING AND CURRENT ROW) AS high_13w,
        max(high) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 25 PRECEDING AND CURRENT ROW) AS high_26w,
        max(high) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 51 PRECEDING AND CURRENT ROW) AS high_52w,
        -- Weekly Low Price Range Indicators
        min(low) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS low_4w,
        min(low) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 12 PRECEDING AND CURRENT ROW) AS low_13w,
        min(low) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 25 PRECEDING AND CURRENT ROW) AS low_26w,
        min(low) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 51 PRECEDING AND CURRENT ROW) AS low_52w,
        -- Weekly Average Volume Indicators
        avg(volume) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS avg_vol_4w,
        avg(volume) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS avg_vol_10w,
        avg(volume) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS avg_vol_30w,
        -- Weekly ATR (Average True Range) Indicators
        avg(weekly_tr) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS atr_10w,
        avg(weekly_tr) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS atr_20w,
        (avg(weekly_tr) OVER (PARTITION BY ticker ORDER BY week_start ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)) / nullIf(`close`, 0) * 100 AS atr_10w_pct
    FROM weekly_with_true_range
)
SELECT
    *
FROM metrics_calculated_for_all_weeks
WHERE date BETWEEN toMonday(CAST({chunk_start_date:String}, 'Date')) AND toMonday(CAST({chunk_end_date:String}, 'Date'))
  AND date + toIntervalDay(4) <= (SELECT max(date) FROM daily_price_sequence FINAL)
ORDER BY ticker, date;
