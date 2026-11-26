# SigmaRail — Automated Trading with LEAN

SigmaRail helps you develop, test, and run trading rules to make money while
controlling risk. The rules identify what to trade, when to buy and sell, how
much to trade, and what limits to follow. You can backtest them on historical
data, then run them live through your brokerage.

SigmaRail is open source so anyone—a person or an automated agent—can trace a
trade from the math behind it to the code and resulting order. That transparency
lets people review and test the logic themselves and gives automation a clear
process to follow.

## From a trading idea to live orders

Start by defining a screen: the rules that decide which stocks qualify. Backtest
the screen to see which stocks it would have selected over time. Then build a
strategy that says what to buy or sell, when to act, how much to trade, and what
limits to follow. Backtest the complete strategy to simulate its trades and
portfolio results, then compare runs and review the orders, trades, and performance.

LEAN organizes a strategy's rules into five parts:

- **Universe:** which stocks the strategy is allowed to trade.
- **Alpha:** the conditions that tell it when to buy or sell.
- **Portfolio Construction:** how much to hold in each stock.
- **Risk Management:** limits on positions and conditions for reducing or exiting them.
- **Execution:** how and when orders are sent and handled.

When you run a strategy live, LEAN uses current market data and sends real orders
through the connected brokerage. Screens, charts, watchlists, and market views
support the work of finding and evaluating trading opportunities.

## Why use explicit trading rules

Trading decisions need to be repeatable, reviewable, and under your control.
SigmaRail expresses a strategy as rules you can backtest, compare, and run through
LEAN in live markets. You can examine what led to an order and set risk limits
before capital is exposed. An AI agent can help explore or develop an idea, while
the trading system follows the strategy you chose instead of improvising decisions
as it runs.

## Get started

The commands below install SigmaRail's data and screening tools. They do not start
Studio's web application.

### Install

Requires Python 3.10 or newer.

```bash
git clone https://github.com/SigmaRail/sigmarail.git
cd sigmarail
python3 -m venv .venv
.venv/bin/python -m pip install -e 'packages/sigmarail-spec[build,test]' -e '.[dev]' -e './studio[dev]'
```

### Connect data and build the screening tables

You need a running ClickHouse server. Loading Sharadar data also requires access to
Sharadar and an API key; SigmaRail does not include market-data files or credentials.

1. Copy `config.yaml.example` to SigmaRail's user configuration directory and add
   your ClickHouse connection details and Sharadar key. The default directory is
   `~/.config/sigmarail` on Linux, `~/Library/Application Support/sigmarail` on macOS,
   or `%APPDATA%\sigmarail` on Windows. Keep credentials private; do not commit them.
2. Preview the schema plan with `.venv/bin/sigmarail-schema`.
3. Apply the schema with `.venv/bin/sigmarail-schema --apply`.
4. Install Studio's database tables with `.venv/bin/sigmarail-studio-schema`.
5. Download and load Sharadar data with `.venv/bin/sigmarail-load --download`.
6. Build derived screening tables with `.venv/bin/sigmarail-populate --metrics all`.

For isolated testing, pass `--mode test` to the supported commands; SigmaRail
protects the configured production database from test-mode writes. The schema
command is read-only unless you pass `--apply`. See [optional data modules](docs/OPTIONAL_DATA_MODULES.md) for modules
that define schema but do not yet include provider loaders.

### Run the Studio application

The checked-in Compose setup is currently configured for the SigmaRail development
Mac. It expects local environment files, existing Postgres and Redis volumes, a
native ClickHouse service, and a mounted LEAN workspace. It is not yet a portable
one-command install for a clean machine. See the [local Docker runtime guide](docs/PRIMARY_DOCKER_RUNTIME.md)
for its requirements and start/update commands.

## How SigmaRail is implemented

SigmaRail is implemented across three projects. [SigmaRail Spec](https://github.com/SigmaRail/sigmarail-spec)
defines the product architecture and versioned contracts. This repository implements the data platform,
query services, research and strategy-authoring interface, and its API/MCP adapters. [SigmaRail Lean](https://github.com/SigmaRail/Lean)
integrates ClickHouse with LEAN and executes supported strategies. Studio is the name of the research
and authoring interface inside this SigmaRail implementation; it is not a separate architecture authority.
See the [architecture guide](https://github.com/SigmaRail/sigmarail-spec/blob/main/docs/ARCHITECTURE.md)
before changing contract behavior.

The research workbench includes screens, charts, watchlists, strategy editing,
backtest review, and MCP access. The Python package provides data loading, schema
management, derived screening metrics, and a bounded read-only query API. The
screening schema currently includes 13 Sharadar source tables and their derived
outputs. The field inventory is in [`spec/lineage-manifest.json`](spec/lineage-manifest.json);
see [query API](docs/QUERY_API.md) and [lineage scope](docs/LINEAGE_SCOPE.md) for
technical details.

### Data providers and storage

SigmaRail stores provider data in ClickHouse; ClickHouse is the data store, not a
data provider. The application brings together data from several providers.

| Source | Data used by the application | Access | SigmaRail status |
| --- | --- | --- | --- |
| [Sharadar](https://sharadar.com/) | End-of-day stock and fund prices, company fundamentals, and securities reference data. SigmaRail derives additional technical measures from the daily prices. | Paid subscription and API key. See [prices](https://sharadar.com/prices), [fundamentals](https://sharadar.com/fundamentals), and [API documentation](https://sharadar.com/docs/intro). | Loaded by SigmaRail. |
| [Alpaca Market Data](https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api) | Optional five-minute stock bars. The loader defaults to IEX; SIP requires the matching account entitlement. | Basic includes IEX data at no charge; broader real-time U.S. exchange coverage requires a paid plan. See [feed notes](docs/ALPACA_INTRADAY.md). | Optional SigmaRail loader. |
| [AAII Investor Sentiment Survey](https://www.aaii.com/sentimentsurvey) | Weekly bullish, neutral, and bearish readings from individual investors. | Recent results are public; AAII says the complete historical dataset is available to members. | SigmaRail source integration; loader consolidation is in progress. |
| [Dolt earnings dataset](https://www.dolthub.com/repositories/post-no-preference/earnings) | Street EPS consensus and reported actuals, based on Zacks data republished on Nasdaq pages. | Public dataset under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). It is not a Zacks or Nasdaq product license. | SigmaRail source integration; loader consolidation is in progress. |
| [Yahoo Finance](https://finance.yahoo.com/) | ETF top holdings and sector weights, fetched through `yfinance`. | The existing loader uses no paid API subscription; access is subject to [Yahoo's terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and is not a licensed market-data feed. | SigmaRail source integration; loader consolidation is in progress. |
| [FRED](https://fred.stlouisfed.org/) | CPI-U inflation and real GDP growth series used to calculate macroeconomic regime measures. | The existing importer reads FRED's public CSV endpoint without an API key. | SigmaRail source integration; loader consolidation is in progress. |

These providers are part of SigmaRail's data pipeline. Their ingestion paths are
being consolidated into this repository; the optional modules currently define
their storage schemas, but do not yet run those imports. See
[optional data modules](docs/OPTIONAL_DATA_MODULES.md) for the current boundaries.

SigmaRail uses the open-source [QuantConnect LEAN engine](https://github.com/QuantConnect/Lean).
We maintain a [customized SigmaRail version of LEAN](https://github.com/SigmaRail/Lean)
that integrates ClickHouse as a market-data source, so LEAN can read SigmaRail data
for historical backtests and universe selection.

The scheduled data updater is an optional Docker service. Its setup and credential
handling are described in [`scripts/README.md`](scripts/README.md). It is separate
from the backtest worker and does not start or modify ClickHouse.

## Tests

Run database-free checks with `.venv/bin/python -m pytest`. For ClickHouse-backed
integration tests, run `.venv/bin/python -m pytest --sigmarail-clickhouse`; this
requires Docker and uses synthetic data in a disposable test database. It does not
use Sharadar data. See the test configuration and fixtures in `tests/` for details.

## License and copyright

Original SigmaRail code is Copyright © 2026 Mark Diggory and is licensed under
the [Apache License, Version 2.0](LICENSE). The license grants permission to use,
modify, and distribute the code under its terms; it does not transfer copyright
ownership. Third-party and vendored components retain their own copyright notices
and license terms; see their individual notices and license files. See [NOTICE](NOTICE)
for the SigmaRail attribution.
