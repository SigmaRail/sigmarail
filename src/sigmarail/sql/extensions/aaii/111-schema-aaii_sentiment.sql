-- AAII investor sentiment survey (weekly)

CREATE TABLE IF NOT EXISTS aaii_sentiment_survey
(
    `survey_date` Date COMMENT 'AAII survey week ending date',
    `bullish_pct` Float64,
    `neutral_pct` Float64,
    `bearish_pct` Float64,
    `bull_bear_spread` Float64 COMMENT 'bullish - bearish',
    `source_url` String DEFAULT 'https://www.aaii.com/sentiment-survey',
    `fetched_at` DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(fetched_at)
ORDER BY (survey_date)
SETTINGS index_granularity = 8192;
