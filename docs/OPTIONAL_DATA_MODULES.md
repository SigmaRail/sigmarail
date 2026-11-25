# Optional data modules

SigmaRail's default contract remains the Sharadar-derived core. External and
provider-backed domains are packaged as opt-in schema modules; selecting a
module adds its tables and views to the configured database without adding
columns to core tables.

| Module | Domain | Tables | External data packaged? |
| --- | --- | --- | --- |
| `analyst_estimates` | Analyst consensus, reported actuals, daily projection | `ext_analyst_estimates_analyst_consensus_asof`, `ext_analyst_estimates_analyst_actuals`, `ext_analyst_estimates_screener_estimates_daily` | No |
| `aaii` | Weekly investor sentiment survey | `ext_aaii_sentiment_survey` | No |
| `etf` | ETF classifications/holdings, index proxies | `ext_etf_etf_classifications`, `ext_etf_etf_holdings_snapshot`, `ext_etf_etf_sector_weights_snapshot`, `ext_etf_index_proxy_catalog` | No |
| `macro` | Daily macroeconomic series and regime labels | `ext_macro_economic_daily` | No |

The module SQL describes storage contracts and views. It contains no provider
observations, credentials, downloaded files, or curated holdings rows. Core
tables remain unchanged. These schemas correspond to existing SigmaRail source
integrations: AAII's weekly sentiment survey, a public Dolt dataset of
Street earnings consensus and actuals, Yahoo Finance ETF holdings and sector
weights, and FRED CPI-U and real GDP series. Their ingestion paths are being
consolidated into this repository. The analyst dataset is documented as CC BY-SA
4.0 and is not a licensed Zacks or Nasdaq feed.
See the [SigmaRail README](../README.md#data-providers-and-storage) for the
source list and access notes. The module manifests and table contracts are in
`src/sigmarail/sql/extensions/`; regenerate contracts after SQL changes with:

```bash
python tools/generate_extension_contracts.py
python tools/generate_extension_contracts.py --check
```

Preview or apply an optional schema explicitly:

```bash
sigmarail-schema --module macro
sigmarail-schema --module macro --apply
sigmarail-schema --module aaii --module etf --apply
```

Populate remains core-only unless a module is selected. When selected, only
transform targets declared in the combined core and module contracts are
eligible for `--metrics all` or `--rebuild`:

```bash
sigmarail-populate --module analyst_estimates --metrics all
```

Provider ingestion is a separate operation from schema installation. This
SigmaRail release packages the schema contracts; loader consolidation is in progress.
The existing sources and their access terms still apply during the migration.
Nothing is downloaded or loaded by `sigmarail-schema` or `sigmarail-populate`
unless an explicit data load command is invoked.

The leveraged ETF surrogate catalog is intentionally excluded here: it maps
securities to trading instruments and belongs with a trading/strategy layer,
not the market-data schema.

Macro calculations based on latest revised public series are not point-in-time
safe for historical strategy evaluation. A future macro loader must either
preserve release/vintage dates or clearly label latest-vintage output as
exploratory, and should not silently present revised values as historical
availability.
