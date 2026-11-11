-- Sharadar SF2/SF3A ownership signals (institutional 13F + insider Form 4).
-- Populated by 85-ownership-signals-daily.sql; joined into daily_screener via 102.

CREATE TABLE IF NOT EXISTS ownership_signals_daily
(
    `ticker` String COMMENT 'Ticker symbol',
    `date` Date COMMENT 'Trading session date (PIT as-of this date)',
    `lastupdated` DateTime('America/New_York') DEFAULT now() COMMENT 'Row update timestamp',
    `inst_calendardate` Nullable(Date) COMMENT 'Latest complete quarter eligible for PIT on date',
    `inst_public_asof_date` Nullable(Date) COMMENT 'inst_calendardate + 45d — first session allowed to use quarter',
    `inst_calendardate_complete` UInt8 COMMENT '1 when quarter passes holder-count quality gate',
    `inst_data_lag_days` UInt16 COMMENT 'date - inst_public_asof_date (public filing staleness)',
    `inst_holdings_lag_days` UInt16 COMMENT 'date - inst_calendardate (holdings snapshot age)',
    `inst_shrholders` UInt32 COMMENT 'Institutional shareholder count (sf3a.shrholders)',
    `inst_shrholders_prev` UInt32 COMMENT 'Prior complete quarter shareholder count',
    `inst_shrholders_qoq_delta` Int32 COMMENT 'QoQ change in institutional holders',
    `inst_shrholders_qoq_pct` Float32 COMMENT 'QoQ pct change in institutional holders',
    `inst_shrunits` Float64 COMMENT 'Institutional share units held',
    `inst_shrunits_qoq_pct` Float32 COMMENT 'QoQ pct change in share units',
    `inst_shrvalue` Float64 COMMENT 'USD value of institutional share holdings',
    `inst_sponsor_trend` Enum8('stable' = 0, 'rising' = 1, 'falling' = 2) COMMENT 'rising if delta>=+3 holders; falling if delta<=-3; else stable',
    `insider_open_buys_90d` UInt16 COMMENT 'Count of qualifying open-market buys (P+NA/DA) in 90d',
    `insider_open_sells_90d` UInt16 COMMENT 'Count of qualifying open-market sells (S+ND/DD) in 90d',
    `insider_open_buy_value_90d` Float64 COMMENT 'Sum of capped buy transaction values in 90d',
    `insider_open_sell_value_90d` Float64 COMMENT 'Sum of capped sell transaction values in 90d',
    `insider_net_buy_value_90d` Float64 COMMENT 'Buy value minus sell value in 90d',
    `insider_officer_buys_90d` UInt16 COMMENT 'Officer open-market buys in 90d',
    `insider_officer_sells_90d` UInt16 COMMENT 'Officer open-market sells in 90d',
    `insider_cluster_buy_flag` UInt8 COMMENT '1 when 3+ owners in 7d window or 2+ officers same filing day (30d)',
    `insider_days_since_open_buy` UInt16 COMMENT 'Days since last qualifying buy; 65535 if none',
    `insider_days_since_open_sell` UInt16 COMMENT 'Days since last qualifying sell; 65535 if none',
    `insider_last_filingdate` Nullable(Date) COMMENT 'Max filingdate in 90d insider window',
    `insider_filing_lag_days` UInt16 COMMENT 'date - transactiondate of latest buy in window',
    `insider_sentiment_90d` Enum8('neutral' = 0, 'net_buy' = 1, 'net_sell' = 2) COMMENT 'net_buy/net_sell when |net value| > $250k; else neutral'
)
ENGINE = ReplacingMergeTree(lastupdated)
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date)
SETTINGS index_granularity = 8192;

-- Managed transform view for target: ownership_signals_daily
-- Ownership signals from Sharadar SF2 (insider) and SF3A (institutional).
-- PIT rules: sf3a quarter date + 45d publication lag; sf2 filing date <= session_date.
--
DROP VIEW IF EXISTS xform_ownership_signals_daily;

CREATE VIEW IF NOT EXISTS xform_ownership_signals_daily
COMMENT '{"order":85,"target":"ownership_signals_daily","sources":["daily_metrics","sf3a","sf2"],"chunk_size":"1w"}'
AS
WITH
chunk_start AS (
    SELECT toDate({chunk_start_date:String}) AS d
),
chunk_end AS (
    SELECT toDate({chunk_end_date:String}) AS d
),
sessions AS (
    SELECT ticker, date
    FROM daily_metrics FINAL
    WHERE date BETWEEN (SELECT d FROM chunk_start) AND (SELECT d FROM chunk_end)
),
sf3_enriched AS (
    SELECT
        ticker,
        date AS calendardate,
        toUInt32(shrholders) AS shrholders,
        shrunits,
        shrvalue,
        date + INTERVAL 45 DAY AS public_asof_date,
        lagInFrame(toUInt32(shrholders), 1) OVER (
            PARTITION BY ticker ORDER BY date
        ) AS shrholders_lag1,
        lagInFrame(shrunits, 1) OVER (
            PARTITION BY ticker ORDER BY date
        ) AS shrunits_lag1
    FROM sf3a FINAL
    WHERE ticker IN (SELECT DISTINCT ticker FROM sessions)
),
sf3_pit AS (
    SELECT
        pit_sess.ticker,
        pit_sess.date AS session_date,
        argMaxIf(
            s.calendardate,
            s.calendardate,
            s.public_asof_date <= pit_sess.date
            AND (
                s.shrholders >= greatest(50, toUInt32(0.5 * coalesce(s.shrholders_lag1, 0)))
                OR dateDiff('day', s.calendardate, pit_sess.date) >= 180
            )
        ) AS inst_calendardate
    FROM sessions AS pit_sess
    INNER JOIN sf3_enriched AS s ON pit_sess.ticker = s.ticker
    WHERE s.public_asof_date <= pit_sess.date
    GROUP BY pit_sess.ticker, pit_sess.date
),
inst_base AS (
    SELECT
        p.ticker,
        p.session_date AS date,
        p.inst_calendardate,
        cur.public_asof_date AS inst_public_asof_date,
        toUInt8(
            cur.shrholders >= greatest(50, toUInt32(0.5 * coalesce(cur.shrholders_lag1, 0)))
        ) AS inst_calendardate_complete,
        toUInt16(greatest(0, dateDiff('day', cur.public_asof_date, p.session_date))) AS inst_data_lag_days,
        toUInt16(greatest(0, dateDiff('day', cur.calendardate, p.session_date))) AS inst_holdings_lag_days,
        toUInt32(cur.shrholders) AS inst_shrholders,
        cur.shrunits AS inst_shrunits,
        cur.shrvalue AS inst_shrvalue
    FROM sf3_pit AS p
    LEFT JOIN sf3_enriched AS cur
        ON p.ticker = cur.ticker AND p.inst_calendardate = cur.calendardate
),
inst_prev AS (
    SELECT
        ib.ticker,
        ib.date,
        argMaxIf(
            toUInt32(s.shrholders),
            s.calendardate,
            s.calendardate < ib.inst_calendardate
            AND (
                s.shrholders >= greatest(50, toUInt32(0.5 * coalesce(s.shrholders_lag1, 0)))
                OR dateDiff('day', s.calendardate, ib.date) >= 180
            )
        ) AS inst_shrholders_prev,
        argMaxIf(
            s.shrunits,
            s.calendardate,
            s.calendardate < ib.inst_calendardate
            AND (
                s.shrholders >= greatest(50, toUInt32(0.5 * coalesce(s.shrholders_lag1, 0)))
                OR dateDiff('day', s.calendardate, ib.date) >= 180
            )
        ) AS inst_shrunits_prev
    FROM inst_base AS ib
    INNER JOIN sf3_enriched AS s ON ib.ticker = s.ticker
    WHERE ib.inst_calendardate IS NOT NULL
      AND s.calendardate < ib.inst_calendardate
    GROUP BY ib.ticker, ib.date
),
inst AS (
    SELECT
        ib.ticker,
        ib.date,
        ib.inst_calendardate,
        ib.inst_public_asof_date,
        ib.inst_calendardate_complete,
        ib.inst_data_lag_days,
        ib.inst_holdings_lag_days,
        ib.inst_shrholders,
        coalesce(ip.inst_shrholders_prev, toUInt32(0)) AS inst_shrholders_prev,
        toInt32(ib.inst_shrholders - coalesce(ip.inst_shrholders_prev, toUInt32(0))) AS inst_shrholders_qoq_delta,
        if(
            coalesce(ip.inst_shrholders_prev, toUInt32(0)) > 0,
            (ib.inst_shrholders - ip.inst_shrholders_prev) / ip.inst_shrholders_prev * 100,
            CAST(0 AS Float32)
        ) AS inst_shrholders_qoq_pct,
        ib.inst_shrunits,
        if(
            coalesce(ip.inst_shrunits_prev, 0) != 0,
            (ib.inst_shrunits - ip.inst_shrunits_prev) / ip.inst_shrunits_prev * 100,
            CAST(0 AS Float32)
        ) AS inst_shrunits_qoq_pct,
        ib.inst_shrvalue,
        CAST(
            multiIf(
                toInt32(ib.inst_shrholders - coalesce(ip.inst_shrholders_prev, toUInt32(0))) >= 3, 'rising',
                toInt32(ib.inst_shrholders - coalesce(ip.inst_shrholders_prev, toUInt32(0))) <= -3, 'falling',
                'stable'
            ) AS Enum8('stable' = 0, 'rising' = 1, 'falling' = 2)
        ) AS inst_sponsor_trend
    FROM inst_base AS ib
    LEFT JOIN inst_prev AS ip ON ib.ticker = ip.ticker AND ib.date = ip.date
),
sf2_qualifying AS (
    SELECT
        ticker,
        date AS filingdate,
        transactiondate,
        ownername,
        isofficer,
        transactioncode,
        least(
            coalesce(
                transactionvalue,
                transactionshares * transactionpricepershare,
                0
            ),
            500000000
        ) AS txn_value_capped
    FROM sf2 FINAL
    WHERE NOT startsWith(formtype, 'RESTATED')
      AND transactioncode IN ('P', 'S')
      AND (
          (transactioncode = 'P' AND securityadcode IN ('NA', 'DA'))
          OR (transactioncode = 'S' AND securityadcode IN ('ND', 'DD'))
      )
      AND coalesce(transactionshares, 0) <= 50000000
      AND date >= (SELECT d FROM chunk_start) - INTERVAL 90 DAY
      AND date <= (SELECT d FROM chunk_end)
      AND ticker IN (SELECT DISTINCT ticker FROM sessions)
),
buy_events AS (
    SELECT *
    FROM sf2_qualifying
    WHERE transactioncode = 'P'
      AND txn_value_capped >= 100000
),
officer_same_day AS (
    SELECT ticker, filingdate
    FROM buy_events
    WHERE isofficer = 'Y'
    GROUP BY ticker, filingdate
    HAVING countDistinct(ownername) >= 2
),
cluster_7d AS (
    SELECT
        b1.ticker,
        b1.filingdate AS anchor_fd
    FROM buy_events AS b1
    INNER JOIN buy_events AS b2
        ON b1.ticker = b2.ticker
       AND b2.filingdate BETWEEN b1.filingdate - 6 AND b1.filingdate + 6
    GROUP BY b1.ticker, b1.filingdate
    HAVING countDistinct(b2.ownername) >= 3
),
insider_agg AS (
    SELECT
        agg_sess.ticker,
        agg_sess.date,
        toUInt16(countIf(s.transactioncode = 'P' AND s.txn_value_capped >= 100000)) AS insider_open_buys_90d,
        toUInt16(countIf(s.transactioncode = 'S' AND s.txn_value_capped >= 100000)) AS insider_open_sells_90d,
        sumIf(s.txn_value_capped, s.transactioncode = 'P') AS insider_open_buy_value_90d,
        sumIf(s.txn_value_capped, s.transactioncode = 'S') AS insider_open_sell_value_90d,
        sumIf(s.txn_value_capped, s.transactioncode = 'P')
            - sumIf(s.txn_value_capped, s.transactioncode = 'S') AS insider_net_buy_value_90d,
        toUInt16(countIf(s.transactioncode = 'P' AND s.isofficer = 'Y' AND s.txn_value_capped >= 100000)) AS insider_officer_buys_90d,
        toUInt16(countIf(s.transactioncode = 'S' AND s.isofficer = 'Y' AND s.txn_value_capped >= 100000)) AS insider_officer_sells_90d,
        max(s.filingdate) AS insider_last_filingdate,
        maxIf(s.filingdate, s.transactioncode = 'P') AS last_buy_filingdate,
        maxIf(s.filingdate, s.transactioncode = 'S') AS last_sell_filingdate,
        argMaxIf(s.transactiondate, s.filingdate, s.transactioncode = 'P') AS latest_buy_txn_date
    FROM sessions AS agg_sess
    LEFT JOIN sf2_qualifying AS s
        ON agg_sess.ticker = s.ticker
       AND s.filingdate <= agg_sess.date
       AND s.filingdate >= agg_sess.date - INTERVAL 90 DAY
    GROUP BY agg_sess.ticker, agg_sess.date
),
inst_join AS (
    SELECT
        ticker AS _jt,
        date AS _jd,
        inst_calendardate,
        inst_public_asof_date,
        inst_calendardate_complete,
        inst_data_lag_days,
        inst_holdings_lag_days,
        inst_shrholders,
        inst_shrholders_prev,
        inst_shrholders_qoq_delta,
        inst_shrholders_qoq_pct,
        inst_shrunits,
        inst_shrunits_qoq_pct,
        inst_shrvalue,
        inst_sponsor_trend
    FROM inst
),
insider_agg_join AS (
    SELECT
        ticker AS _jt,
        date AS _jd,
        insider_open_buys_90d,
        insider_open_sells_90d,
        insider_open_buy_value_90d,
        insider_open_sell_value_90d,
        insider_net_buy_value_90d,
        insider_officer_buys_90d,
        insider_officer_sells_90d,
        insider_last_filingdate,
        last_buy_filingdate,
        last_sell_filingdate,
        latest_buy_txn_date
    FROM insider_agg
),
ownership_step1 AS (
    SELECT
        dm.ticker,
        dm.date,
        i.inst_calendardate,
        i.inst_public_asof_date,
        i.inst_calendardate_complete,
        i.inst_data_lag_days,
        i.inst_holdings_lag_days,
        i.inst_shrholders,
        i.inst_shrholders_prev,
        i.inst_shrholders_qoq_delta,
        i.inst_shrholders_qoq_pct,
        i.inst_shrunits,
        i.inst_shrunits_qoq_pct,
        i.inst_shrvalue,
        i.inst_sponsor_trend
    FROM sessions AS dm
    LEFT JOIN inst_join AS i ON dm.ticker = i._jt AND dm.date = i._jd
),
ownership_step2 AS (
    SELECT
        s.ticker,
        s.date,
        s.inst_calendardate,
        s.inst_public_asof_date,
        s.inst_calendardate_complete,
        s.inst_data_lag_days,
        s.inst_holdings_lag_days,
        s.inst_shrholders,
        s.inst_shrholders_prev,
        s.inst_shrholders_qoq_delta,
        s.inst_shrholders_qoq_pct,
        s.inst_shrunits,
        s.inst_shrunits_qoq_pct,
        s.inst_shrvalue,
        s.inst_sponsor_trend,
        ia.insider_open_buys_90d,
        ia.insider_open_sells_90d,
        ia.insider_open_buy_value_90d,
        ia.insider_open_sell_value_90d,
        ia.insider_net_buy_value_90d,
        ia.insider_officer_buys_90d,
        ia.insider_officer_sells_90d,
        ia.insider_last_filingdate,
        ia.last_buy_filingdate,
        ia.last_sell_filingdate,
        ia.latest_buy_txn_date
    FROM ownership_step1 AS s
    LEFT JOIN insider_agg_join AS ia ON s.ticker = ia._jt AND s.date = ia._jd
),
ownership_out AS (
    SELECT
        s.ticker,
        s.date,
        any(s.inst_calendardate) AS inst_calendardate,
        any(s.inst_public_asof_date) AS inst_public_asof_date,
        any(s.inst_calendardate_complete) AS inst_calendardate_complete,
        any(s.inst_data_lag_days) AS inst_data_lag_days,
        any(s.inst_holdings_lag_days) AS inst_holdings_lag_days,
        any(s.inst_shrholders) AS inst_shrholders,
        any(s.inst_shrholders_prev) AS inst_shrholders_prev,
        any(s.inst_shrholders_qoq_delta) AS inst_shrholders_qoq_delta,
        any(s.inst_shrholders_qoq_pct) AS inst_shrholders_qoq_pct,
        any(s.inst_shrunits) AS inst_shrunits,
        any(s.inst_shrunits_qoq_pct) AS inst_shrunits_qoq_pct,
        any(s.inst_shrvalue) AS inst_shrvalue,
        any(s.inst_sponsor_trend) AS inst_sponsor_trend,
        any(s.insider_open_buys_90d) AS insider_open_buys_90d,
        any(s.insider_open_sells_90d) AS insider_open_sells_90d,
        any(s.insider_open_buy_value_90d) AS insider_open_buy_value_90d,
        any(s.insider_open_sell_value_90d) AS insider_open_sell_value_90d,
        any(s.insider_net_buy_value_90d) AS insider_net_buy_value_90d,
        any(s.insider_officer_buys_90d) AS insider_officer_buys_90d,
        any(s.insider_officer_sells_90d) AS insider_officer_sells_90d,
        any(s.insider_last_filingdate) AS insider_last_filingdate,
        any(s.last_buy_filingdate) AS last_buy_filingdate,
        any(s.last_sell_filingdate) AS last_sell_filingdate,
        any(s.latest_buy_txn_date) AS latest_buy_txn_date,
        toUInt8(
            max(if(o.ticker != '', 1, 0))
            OR max(if(c.ticker != '', 1, 0))
        ) AS insider_cluster_buy_flag
    FROM ownership_step2 AS s
    LEFT JOIN officer_same_day AS o
        ON s.ticker = o.ticker
       AND o.filingdate <= s.date
       AND o.filingdate >= s.date - INTERVAL 30 DAY
    LEFT JOIN cluster_7d AS c
        ON s.ticker = c.ticker
       AND c.anchor_fd <= s.date
       AND c.anchor_fd >= s.date - INTERVAL 30 DAY
    GROUP BY s.ticker, s.date
)
SELECT
    s.ticker AS ticker,
    s.date AS date,
    now() AS lastupdated,
    s.inst_calendardate,
    s.inst_public_asof_date,
    coalesce(s.inst_calendardate_complete, toUInt8(0)) AS inst_calendardate_complete,
    coalesce(s.inst_data_lag_days, toUInt16(0)) AS inst_data_lag_days,
    coalesce(s.inst_holdings_lag_days, toUInt16(0)) AS inst_holdings_lag_days,
    coalesce(s.inst_shrholders, toUInt32(0)) AS inst_shrholders,
    coalesce(s.inst_shrholders_prev, toUInt32(0)) AS inst_shrholders_prev,
    coalesce(s.inst_shrholders_qoq_delta, toInt32(0)) AS inst_shrholders_qoq_delta,
    coalesce(s.inst_shrholders_qoq_pct, CAST(0 AS Float32)) AS inst_shrholders_qoq_pct,
    coalesce(s.inst_shrunits, 0) AS inst_shrunits,
    coalesce(s.inst_shrunits_qoq_pct, CAST(0 AS Float32)) AS inst_shrunits_qoq_pct,
    coalesce(s.inst_shrvalue, 0) AS inst_shrvalue,
    coalesce(
        s.inst_sponsor_trend,
        CAST('stable' AS Enum8('stable' = 0, 'rising' = 1, 'falling' = 2))
    ) AS inst_sponsor_trend,
    coalesce(s.insider_open_buys_90d, toUInt16(0)) AS insider_open_buys_90d,
    coalesce(s.insider_open_sells_90d, toUInt16(0)) AS insider_open_sells_90d,
    coalesce(s.insider_open_buy_value_90d, 0) AS insider_open_buy_value_90d,
    coalesce(s.insider_open_sell_value_90d, 0) AS insider_open_sell_value_90d,
    coalesce(s.insider_net_buy_value_90d, 0) AS insider_net_buy_value_90d,
    coalesce(s.insider_officer_buys_90d, toUInt16(0)) AS insider_officer_buys_90d,
    coalesce(s.insider_officer_sells_90d, toUInt16(0)) AS insider_officer_sells_90d,
    coalesce(s.insider_cluster_buy_flag, toUInt8(0)) AS insider_cluster_buy_flag,
    if(
        s.last_buy_filingdate IS NULL OR s.last_buy_filingdate = toDate('1970-01-01'),
        toUInt16(65535),
        toUInt16(dateDiff('day', s.last_buy_filingdate, s.date))
    ) AS insider_days_since_open_buy,
    if(
        s.last_sell_filingdate IS NULL OR s.last_sell_filingdate = toDate('1970-01-01'),
        toUInt16(65535),
        toUInt16(dateDiff('day', s.last_sell_filingdate, s.date))
    ) AS insider_days_since_open_sell,
    s.insider_last_filingdate,
    if(
        s.latest_buy_txn_date IS NULL OR s.latest_buy_txn_date = toDate('1970-01-01'),
        toUInt16(0),
        toUInt16(greatest(0, dateDiff('day', s.latest_buy_txn_date, s.date)))
    ) AS insider_filing_lag_days,
    CAST(
        multiIf(
            coalesce(s.insider_net_buy_value_90d, 0) > 250000
                AND coalesce(s.insider_open_buys_90d, toUInt16(0)) > coalesce(s.insider_open_sells_90d, toUInt16(0)),
            'net_buy',
            coalesce(s.insider_net_buy_value_90d, 0) < -250000,
            'net_sell',
            'neutral'
        ) AS Enum8('neutral' = 0, 'net_buy' = 1, 'net_sell' = 2)
    ) AS insider_sentiment_90d
FROM ownership_out AS s;
