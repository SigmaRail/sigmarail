# SigmaRail — Local Stock Research and Automated Trading

SigmaRail is an open-source platform for researching U.S. stocks, testing strategies,
and trading them automatically. You can run the entire platform on your own hardware.
Its ClickHouse data warehouse stores the historical market data you load and the
indicators SigmaRail calculates from it. The warehouse stays local and can be updated
when you import more data. Studio uses the warehouse to explore stocks and market
conditions over time and to screen historical data. The trading engine uses it to
test strategies against historical prices and screening results.

## Study stocks and market conditions over time

Run a screen on historical dates to see which stocks met your criteria on each date.
Track when stocks entered or left the list as their prices and indicators changed.
For example, screen for stocks above rising long-term moving averages with strong
relative strength, then follow which stocks continued to qualify through a market
decline and recovery.

SigmaRail defines its indicators and screening metrics in readable SQL views. You can
inspect the formulas and source fields, reproduce a calculation, or recreate a screen
from another trading system and test it against your own historical data.

## Use your screens in trading strategies

Use the same expression language to define stock screens and strategy rules. A screen
sets which stocks are eligible to trade on each date of a backtest. Strategy rules say
when to buy or sell, how much to hold, and when to reduce or exit a position. Backtest
the strategy, compare runs, and review simulated orders, fills, returns, and drawdowns.

SigmaRail's customized version of QuantConnect LEAN runs backtests using historical
prices and volume from ClickHouse. It also requests the eligible stock list from
SigmaRail's screening service, so the screen's rules determine which stocks the
strategy can trade on each date. After reviewing a backtest, deploy that strategy to
a configured paper or live brokerage account. In live trading, LEAN processes your
live data feed and submits orders through the brokerage. Studio shows the deployment
status, holdings, and recent orders.

## Work with AI agents

SigmaRail's MCP connector describes the platform, its datasets, expressions, and tools
to AI agents as they work. Agents can use that information to draft screens and
strategy specifications for you to review and backtest.

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

You need a running ClickHouse server and a data source whose terms permit your
intended use. SigmaRail does not provide market data, provider accounts, API
credentials, or data licenses. The core database schema currently follows
Sharadar's data format. If you have a Sharadar subscription, its importer can
download your data into the ClickHouse instance you configure. Sharadar is one
external source option; SigmaRail is not affiliated with or endorsed by it.

1. Copy `config.yaml.example` to SigmaRail's user configuration directory and add
   your ClickHouse connection details and, if you choose Sharadar, your own
   Sharadar API key. The default directory is
   `~/.config/sigmarail` on Linux, `~/Library/Application Support/sigmarail` on macOS,
   or `%APPDATA%\sigmarail` on Windows. Keep credentials private; do not commit them.
2. Preview the schema plan with `.venv/bin/sigmarail-schema`.
3. Apply the schema with `.venv/bin/sigmarail-schema --apply`.
4. Install Studio's database tables with `.venv/bin/sigmarail-studio-schema`.
5. Download and load Sharadar data with `.venv/bin/sigmarail-load --download`.
6. Build derived screening tables with `.venv/bin/sigmarail-populate --metrics all`.

For isolated testing, pass `--mode test` to the supported commands; SigmaRail
protects the configured production database from test-mode writes. The schema
command is read-only unless you pass `--apply`. See the
[optional data modules](docs/OPTIONAL_DATA_MODULES.md) documentation for
integrations that define schema but do not yet include provider loaders.

### Run the Studio application

The checked-in Compose setup is currently configured for the SigmaRail development
Mac. It expects local environment files, existing Postgres and Redis volumes, a
native ClickHouse service, and a mounted LEAN workspace. It is not yet a portable
one-command install for a clean machine. See the
[local Docker runtime guide](docs/PRIMARY_DOCKER_RUNTIME.md) for its requirements
and start/update commands.

## How SigmaRail is implemented

The research workbench includes screens, charts, watchlists, strategy editing,
backtest review, and MCP access. The Python package loads data, manages the database
schema, calculates screening metrics, and provides a read-only query interface. The
current core schema includes 13 Sharadar source tables and derived data. See the
[field inventory](spec/lineage-manifest.json), [query API](docs/QUERY_API.md), and
[lineage scope](docs/LINEAGE_SCOPE.md) for technical details.

### Data providers and storage

SigmaRail can store data in the ClickHouse instance configured by the user;
ClickHouse is a data store, not a data provider. The provider names below identify
upstream sources and integrations, not partnerships, recommendations, or endorsements.
Each provider controls its own access and license terms.

| Source | Role in SigmaRail | Access and integration |
| --- | --- | --- |
| [Sharadar](https://sharadar.com/) | Data used by core tables, including end-of-day stock and fund prices, fundamentals, and securities reference data. | The optional importer uses a Sharadar API key supplied by the user and writes to the user's ClickHouse database. Users must obtain a license that permits their intended use. See [prices](https://sharadar.com/prices), [fundamentals](https://sharadar.com/fundamentals), [API docs](https://sharadar.com/docs/intro), and [Sharadar's terms](https://sharadar.com/terms). SigmaRail provides no Sharadar account, key, data, or license. |
| [Alpaca Market Data](https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api) | Optional five-minute stock bars. | The optional importer uses credentials and feed entitlements supplied by the user. See [feed notes](docs/ALPACA_INTRADAY.md) and Alpaca's terms. |
| [AAII Investor Sentiment Survey](https://www.aaii.com/sentimentsurvey) | Weekly investor-sentiment readings. | Access to complete historical data is subject to AAII's terms and membership. |
| [Dolt earnings dataset](https://www.dolthub.com/repositories/post-no-preference/earnings) | Street EPS consensus and reported actuals. | The public dataset is under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); that does not grant a Zacks or Nasdaq product license. |
| [Yahoo Finance](https://finance.yahoo.com/) | ETF holdings and sector weights fetched through `yfinance`. | Access is subject to [Yahoo's terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html); this is not a licensed market-data feed. |
| [FRED](https://fred.stlouisfed.org/) | Public macroeconomic series. | The importer reads FRED's public CSV endpoint; use remains subject to FRED's terms. |

Integration status varies: a provider listed here or a schema for its data does
not mean SigmaRail provides access, a subscription, or a data license. Where an
importer is available, it makes requests using credentials supplied by the user
and stores the result in the user's configured environment. The user is
responsible for obtaining required rights and managing downloaded data—including
storage, retention, access, and deletion—under the provider's terms. Do not
redistribute provider data through SigmaRail unless the applicable provider
license expressly permits it. See [optional data modules](docs/OPTIONAL_DATA_MODULES.md)
for the current schema and integration boundaries.

Backtesting and live trading in SigmaRail are based on the open-source
[QuantConnect LEAN engine](https://github.com/QuantConnect/Lean). SigmaRail provides
a [customized version of LEAN](https://github.com/SigmaRail/Lean) that integrates
ClickHouse as a live data source, so LEAN can read SigmaRail data directly from the
database.

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
for attribution and the distinction between the code license and third-party data.

The Apache license applies to SigmaRail code only. It does not grant rights to
third-party datasets, provider APIs, credentials, or trademarks. Provider data
and services are not included with SigmaRail. Users must obtain any required
provider subscription and license directly, confirm that it permits their
intended personal, professional, or organizational use, and follow its
conditions for storage, retention, display, derived data, and redistribution.
Listing a provider or including an optional integration does not imply
affiliation, endorsement, or that a particular provider plan permits a particular
use of SigmaRail.
