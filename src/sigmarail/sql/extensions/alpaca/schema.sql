-- Alpaca-owned data stays outside SigmaRail's Sharadar-owned core schema.
CREATE TABLE IF NOT EXISTS ext_alpaca_price
(
    `ticker` String COMMENT 'Provider ticker symbol supplied explicitly to the import; not a point-in-time universe definition',
    `timestamp_utc` DateTime64(3, 'UTC') COMMENT 'Start timestamp of the five-minute bar in UTC',
    `session_date` Date COMMENT 'US equity session date in America/New_York',
    `open` Float64 COMMENT 'Raw or provider-adjusted open according to adjustment',
    `high` Float64 COMMENT 'Raw or provider-adjusted high according to adjustment',
    `low` Float64 COMMENT 'Raw or provider-adjusted low according to adjustment',
    `close` Float64 COMMENT 'Raw or provider-adjusted close according to adjustment',
    `volume` Float64 COMMENT 'Five-minute volume returned by Alpaca',
    `trade_count` Nullable(UInt64) COMMENT 'Number of trades when supplied by Alpaca',
    `vwap` Nullable(Float64) COMMENT 'Alpaca five-minute volume-weighted average price when supplied',
    `feed` LowCardinality(String) COMMENT 'Alpaca market-data feed: sip or iex',
    `adjustment` LowCardinality(String) COMMENT 'Alpaca adjustment request: raw, split, dividend, spin-off, or all',
    `ingested_at` DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Import timestamp; later rows replace the same key and preserve provider corrections'
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(session_date)
ORDER BY (ticker, timestamp_utc, feed, adjustment);

CREATE TABLE IF NOT EXISTS ext_alpaca_market_calendar
(
    `session_date` Date COMMENT 'US equity session date in America/New_York',
    `session_open_utc` DateTime64(3, 'UTC') COMMENT 'Alpaca calendar regular-session open converted to UTC',
    `session_close_utc` DateTime64(3, 'UTC') COMMENT 'Alpaca calendar close in UTC, including early closes',
    `ingested_at` DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Calendar retrieval timestamp'
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(session_date)
ORDER BY session_date;

CREATE VIEW IF NOT EXISTS ext_alpaca_price_65m AS
WITH
    intDiv(dateDiff('minute', cal.session_open_utc, p.timestamp_utc), 65) AS window_index,
    cal.session_open_utc + toIntervalMinute(window_index * 65) AS bar_start_utc,
    least(bar_start_utc + toIntervalMinute(65), cal.session_close_utc) AS bar_end_utc
SELECT
    p.ticker AS ticker,
    cal.session_date AS session_date,
    bar_start_utc,
    bar_end_utc,
    toUInt8(bar_end_utc < bar_start_utc + toIntervalMinute(65)) AS is_short_session_bar,
    toUInt8(dateDiff('minute', bar_start_utc, bar_end_utc) / 5) AS expected_5m_time_slots,
    count() AS observed_5m_bars,
    argMin(p.open, p.timestamp_utc) AS open,
    max(p.high) AS high,
    min(p.low) AS low,
    argMax(p.close, p.timestamp_utc) AS close,
    sum(p.volume) AS volume,
    if(countIf(isNull(p.trade_count)) > 0, CAST(NULL, 'Nullable(UInt64)'), sum(p.trade_count)) AS trade_count,
    sumIf(p.vwap * p.volume, isNotNull(p.vwap)) / nullIf(sumIf(p.volume, isNotNull(p.vwap)), 0) AS vwap,
    p.feed AS feed,
    p.adjustment AS adjustment
FROM ext_alpaca_price AS p FINAL
INNER JOIN ext_alpaca_market_calendar AS cal FINAL ON cal.session_date = p.session_date
WHERE p.timestamp_utc >= cal.session_open_utc
  AND p.timestamp_utc < cal.session_close_utc
GROUP BY p.ticker, cal.session_date, bar_start_utc, bar_end_utc, p.feed, p.adjustment;
