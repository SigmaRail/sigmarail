CREATE TABLE IF NOT EXISTS daily_price_sequence
(
    `date` Date COMMENT 'Trading session date',
    `trade_day_num` UInt32 COMMENT 'Monotonic trading-day index (used for closed-week tests and windowing)'
)
ENGINE = ReplacingMergeTree
ORDER BY (date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: daily_price_sequence
-- =============================================================================
-- Name: 02-daily-price-sequence.sql
-- Description: Populates the daily_price_sequence table.
-- Provide sequential count of days since start of dataset.
-- =============================================================================
--
DROP VIEW IF EXISTS xform_daily_price_sequence;

CREATE VIEW IF NOT EXISTS xform_daily_price_sequence (
    date,
    trade_day_num
)
COMMENT '{"order":0,"target":"daily_price_sequence","sources":["sep","sfp"],"source_timestamp_column":"lastupdated","target_timestamp_column":"none"}'
AS
WITH all_trading_days AS (
    SELECT DISTINCT date FROM sep FINAL
    UNION DISTINCT
    SELECT DISTINCT date FROM sfp FINAL
)
SELECT
    date,
    row_number() OVER (ORDER BY date) as trade_day_num
FROM all_trading_days;
