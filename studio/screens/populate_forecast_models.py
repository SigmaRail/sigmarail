"""Population script for screener_forecast_models_daily table in ClickHouse.

Computes point-in-time forward fundamental forecast projections (1Y & 2Y Forward EPS,
Graham 15x Fair Value Target, Normal P/E Target, 2Y Expected CAGR %, and Forward PEG ratio)
and stores them partitioned by month.
"""

from __future__ import annotations

import argparse
import sys
from screens.ch import get_ch_client


DDL_FORECAST_TABLE = """
CREATE TABLE IF NOT EXISTS screener_forecast_models_daily (
    ticker LowCardinality(String),
    date Date,
    model_type LowCardinality(String) DEFAULT 'historical_cagr_3y',
    growth_rate_pct Float32,
    fwd_eps_1y Float32,
    fwd_eps_2y Float32,
    historical_median_pe Float32,
    target_price_15x Float32,
    target_price_normal_pe Float32,
    fwd_cagr_2y_normal_pe Float32,
    fwd_peg_ratio Float32,
    valuation_spread_pct Float32 DEFAULT 0.0,
    valuation_status LowCardinality(String) DEFAULT 'Fairly Valued',
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (ticker, date, model_type);
"""


POPULATE_SQL = """
INSERT INTO screener_forecast_models_daily (
    ticker, date, model_type, growth_rate_pct, fwd_eps_1y, fwd_eps_2y,
    historical_median_pe, target_price_15x, target_price_normal_pe,
    fwd_cagr_2y_normal_pe, fwd_peg_ratio, valuation_spread_pct, valuation_status
)
SELECT
    f.ticker,
    f.date,
    'historical_cagr_3y' AS model_type,
    round(
        if(f.ary_eps_growth_3y_cagr IS NOT NULL AND f.ary_eps_growth_3y_cagr > -0.5 AND f.ary_eps_growth_3y_cagr < 1.0,
           f.ary_eps_growth_3y_cagr * 100,
           if(f.mrt_roe IS NOT NULL AND f.mrt_roe > 0, f.mrt_roe * 100 * 0.8, 8.0)),
        2
    ) AS growth_rate_pct,
    round(
        f.mrt_epsdil * (1 + (growth_rate_pct / 100)),
        3
    ) AS fwd_eps_1y,
    round(
        f.mrt_epsdil * pow(1 + (growth_rate_pct / 100), 2),
        3
    ) AS fwd_eps_2y,
    20.0 AS historical_median_pe,
    round(fwd_eps_2y * 15.0, 2) AS target_price_15x,
    round(fwd_eps_2y * 20.0, 2) AS target_price_normal_pe,
    round(
        if(p.close > 0 AND target_price_normal_pe > 0,
           (pow(target_price_normal_pe / p.close, 0.5) - 1) * 100,
           0),
        2
    ) AS fwd_cagr_2y_normal_pe,
    round(
        if(growth_rate_pct > 0 AND f.mrt_epsdil > 0 AND p.close > 0,
           (p.close / f.mrt_epsdil) / growth_rate_pct,
           0),
        2
    ) AS fwd_peg_ratio,
    round(
        if(f.mrt_epsdil > 0 AND p.close > 0,
           ((p.close - (f.mrt_epsdil * 20.0)) / (f.mrt_epsdil * 20.0)) * 100,
           0),
        2
    ) AS valuation_spread_pct,
    if(valuation_spread_pct <= -20.0, 'Significantly Undervalued',
       if(valuation_spread_pct <= -5.0, 'Modestly Undervalued',
          if(valuation_spread_pct <= 5.0, 'Fairly Valued',
             if(valuation_spread_pct <= 20.0, 'Modestly Overvalued',
                'Significantly Overvalued')))) AS valuation_status
FROM screener_fundamentals_daily f
INNER JOIN screener_price_tech_daily p ON f.ticker = p.ticker AND f.date = p.date
WHERE f.mrt_epsdil > 0 AND p.close > 0 {date_filter}
"""


def populate_forecast_models(start_date: str | None = None) -> int:
    client = get_ch_client()
    client.command(DDL_FORECAST_TABLE)
    date_filter = f"AND f.date >= '{start_date}'" if start_date else ""
    query = POPULATE_SQL.format(date_filter=date_filter)
    client.command(query)
    count = client.query("SELECT count() FROM screener_forecast_models_daily").result_rows[0][0]
    return int(count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate screener_forecast_models_daily in ClickHouse")
    parser.add_argument("--start-date", default="2024-01-01", help="Start date (YYYY-MM-DD) or empty for full history")
    args = parser.parse_args()
    print(f"Populating forecast models (start_date={args.start_date})...")
    total = populate_forecast_models(args.start_date)
    print(f"Done! Total rows in screener_forecast_models_daily: {total:,}")
