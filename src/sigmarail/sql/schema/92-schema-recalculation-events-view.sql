-- =============================================================================
-- Recalculation Events View
-- Events that drive metrics recalculation (splits, spinoffs, sp500 changes, etc.)
-- Queryable by date with recalculation_start_date for lookback.
-- =============================================================================

DROP VIEW IF EXISTS recalculation_events_view;


CREATE VIEW IF NOT EXISTS recalculation_events_view AS
WITH price_first AS (
    SELECT ticker, min(date) AS first_date FROM sep GROUP BY ticker
    UNION ALL
    SELECT ticker, min(date) AS first_date FROM sfp GROUP BY ticker
),
first_per_ticker AS (
    SELECT ticker, min(first_date) AS first_price_date FROM price_first GROUP BY ticker
),
action_events AS (
    SELECT
        a.date,
        a.action,
        a.ticker,
        a.name,
        a.value,
        a.contraticker,
        coalesce(f.first_price_date, a.date) AS recalculation_start_date,
        'actions' AS source
    FROM actions a FINAL
    LEFT JOIN first_per_ticker f ON f.ticker = a.ticker
    WHERE a.action IN (
        'split', 'spinoff', 'spinoffdividend', 'adrratiosplit', 'dividend',
        'tickerchangefrom', 'tickerchangeto', 'mergerto', 'mergerfrom',
        'acquisitionof', 'acquisitionby', 'delisted', 'bankruptcyliquidation',
        'regulatorydelisting', 'voluntarydelisting'
    )
),
sp500_events AS (
    SELECT
        date,
        action,
        ticker,
        name,
        toNullable(0.0) AS value,
        contraticker,
        date AS recalculation_start_date,
        'sp500' AS source
    FROM sp500 FINAL
    WHERE action IN ('added', 'removed')
)
SELECT * FROM action_events
UNION ALL
SELECT * FROM sp500_events;
