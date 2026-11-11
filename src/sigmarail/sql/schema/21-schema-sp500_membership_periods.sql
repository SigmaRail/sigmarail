CREATE TABLE IF NOT EXISTS sp500_membership_periods
(
    `ticker` LowCardinality(String) COMMENT 'Ticker Symbol, matching sp500 table.',
    `member_start_date` Date COMMENT 'The date the ticker was added to the S&P 500.',
    `member_end_date` Date COMMENT 'The date the ticker was removed from the S&P 500. A far future date (e.g., 2999-12-31) indicates current membership.'
)
ENGINE = ReplacingMergeTree
ORDER BY (ticker, member_start_date)
SETTINGS index_granularity = 8192
COMMENT 'Stores resolved S&P 500 membership periods (start and end dates) for each ticker.';

-- Managed transform view for target: sp500_membership_periods
-- This script populates the sp500_membership_periods table by resolving
-- membership start and end dates from the event-based sp500 table.

-- It is recommended to TRUNCATE TABLE sp500_membership_periods before running this script
-- if it's intended to be a full refresh.
--
DROP VIEW IF EXISTS xform_sp500_membership_periods;

CREATE VIEW IF NOT EXISTS xform_sp500_membership_periods (
    ticker,
    member_start_date,
    member_end_date
)
COMMENT '{"order":0,"target":"sp500_membership_periods","sources":["sp500"],"source_timestamp_column":"lastupdated","target_timestamp_column":"none"}'
AS
WITH
    add_events AS (
        SELECT DISTINCT -- Ensures each ticker/add_date is unique if source has duplicates
            ticker,
            date AS add_date
        FROM sp500
        WHERE action = 'added'
    ),
    -- Find the next add_date for each ticker using a self-join and aggregation
    adds_with_next_add_date_raw AS (
        SELECT
            a1.ticker,
            a1.add_date,
            MIN(a2.add_date) AS next_add_date_candidate -- Min add_date from a2 that is > a1.add_date
        FROM add_events AS a1
        LEFT JOIN add_events AS a2
            ON a1.ticker = a2.ticker
            AND a2.add_date > a1.add_date -- Join condition: same ticker, a2's date strictly after a1's
        GROUP BY
            a1.ticker,
            a1.add_date
    ),
    -- Coalesce null next_add_date_candidate to a far future date
    adds_with_next_add_date AS (
        SELECT
            ticker,
            add_date,
            COALESCE(next_add_date_candidate, toDate('3000-01-01')) AS next_add_date
        FROM adds_with_next_add_date_raw
    ),
    remove_events AS (
        SELECT
            ticker,
            date AS removal_date
        FROM sp500
        WHERE action = 'removed'
    )
SELECT
    ana.ticker,
    ana.add_date AS member_start_date,
    CASE
        -- If there's a removal for this ticker between its add_date and next_add_date
        WHEN MIN(re.removal_date) IS NOT NULL THEN MIN(re.removal_date) - INTERVAL 1 DAY
        -- If no specific removal in that window, and it's the last known add period for the ticker
        WHEN ana.next_add_date = toDate('3000-01-01') THEN toDate('2999-12-31')
        -- If no specific removal, but there IS a subsequent add_date (implies removal before that next_add)
        ELSE ana.next_add_date - INTERVAL 1 DAY
    END AS member_end_date
FROM adds_with_next_add_date AS ana
LEFT JOIN remove_events AS re
    ON ana.ticker = re.ticker
    AND re.removal_date > ana.add_date
    AND re.removal_date < ana.next_add_date -- Only consider removals strictly between this add and the next
GROUP BY
    ana.ticker,
    ana.add_date,
    ana.next_add_date
ORDER BY
    ana.ticker,
    ana.add_date;
