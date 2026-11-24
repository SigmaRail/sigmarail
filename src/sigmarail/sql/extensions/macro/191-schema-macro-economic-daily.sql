-- =============================================================================
-- Macro economic-environment signals (Dalio 4-quadrant regime source)
-- =============================================================================
-- Growth = Real GDP QoQ % change (annualized); Inflation = CPI-U YoY % change.
-- Monthly CPI + quarterly GDP are forward-filled to daily so the economic
-- environment can drive the All Weather regime overlay in backtests.
--
-- Populate with the opt-in SigmaRail macro loader.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ext_macro_economic_daily
(
    `date` Date32,
    `real_gdp_qoq` Float64 COMMENT 'Real GDP QoQ % change, annualized (forward-filled)',
    `cpi_yoy` Float64 COMMENT 'CPI-U YoY % change (forward-filled)',
    `regime_quadrant` LowCardinality(String) COMMENT 'reflation | goldilocks | stagflation | deflation'
)
ENGINE = MergeTree
ORDER BY date
SETTINGS index_granularity = 8192;
