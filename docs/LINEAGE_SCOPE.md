# SigmaRail core lineage boundary

## Inclusion rule

The five dated screener outputs for price/technical, fundamentals, ratings,
stage, and ownership remain the primary core outputs. SigmaRail also includes the
SQL transforms for Sharadar-only factor, forecast, VCP, forward-return,
group-strength, score, RVAB, market-context, canonical-regime, and symbol
technical outputs. The normalized `daily_prices` table is included as a direct
consumer surface. The manifest lists every included table and column, direct
SQL inputs, and Sharadar roots. Each derived column carries the complete root
set for its defining transform; expression-level source-column mapping is not
claimed.

Every listed output with an available SQL transform is included when its
transitive SQL input closure resolves exclusively to the 13 Sharadar source
tables. Application- and portfolio-oriented naming does not by itself exclude
a Sharadar-only transform. Outputs depending on Knowledge Base, analyst, or
other non-Sharadar inputs remain outside this schema.

Lineage is derived from physical table references in the transform SQL, not
only from each view's `COMMENT` source list. During extraction, several source
lists were found to omit real inputs, including `daily_price_sequence`,
`tickers`, `broad_market_constituents`, `sp500_membership_periods`, and
`market_regime_signals_daily`. The copied transform metadata now lists those
actual dependencies so populate scheduling and freshness checks see them.

All 13 raw source tables are schema-only in this repository:
`actions`, `daily`, `events`, `metrics`, `sep`, `sf1`, `sf2`, `sf3`, `sf3a`,
`sf3b`, `sfp`, `sp500`, and `tickers`. No vendor rows, exports, downloads, or
credentials are included.

Populate order is checked against every declared transform input. The
extracted schedule moves point-in-time classification before its consumers,
places enhanced bear signals before market-regime transforms, and places
ratings after all of its source marts.

## Mixed and deferred fields

`ticker_classification_daily.gic_sector`, `gic_group`, `gic_industry`, and
`gic_subindustry` are reserved for an external classification overlay and are
removed from the SigmaRail schema and entity sidecar. The source transform emitted
empty placeholders for these fields; SigmaRail omits them entirely. The remaining
classification fields come from Sharadar `tickers` and are retained.

KB sentiment marts, analyst consensus/actuals, and estimates are excluded. The
estimates mart has no standalone Sharadar metric columns: its estimate,
revision, and surprise values depend on analyst tables, while its ticker/date
spine is restricted to the analyst-covered universe. A future extension must
keep those tables and fields out of the core schema manifest and populate
command.

## Deferred layers

Portfolio allocations and policy-composed regime/backtest outputs remain
separate layers. Their names and reasons are in the manifest. The included
market context and technical feature tables are Sharadar-only SQL outputs and
are part of the database contract even when an application consumes them.
