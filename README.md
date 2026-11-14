# SigmaRail — Open Securities Analytics Toolkit

SigmaRail is the Sharadar-only ClickHouse data layer for securities analytics. It
contains the source-table schema, point-in-time transforms, and the dated
technical, fundamental, rating, stage, and institutional-ownership tables used
to build a screener.

The Python distribution and default ClickHouse database are both named `sigmarail`.
The package includes `sigmarail-load`, `sigmarail-populate`, and the `sigmarail-schema`
command. `sigmarail-schema` previews the schema plan without changing the database;
rerun with `sigmarail-schema --apply` to execute it. Applying creates all declared
tables first, reconciles their columns and comments against the SQL-derived
contract, then drops views in reverse dependency order and recreates them in
manifest order. The SQL package contains schema definitions and transforms
only; it contains no Sharadar data or credentials.

SigmaRail owns the columns declared for its core tables. Local plugins and other
extensions must store their data in separate namespaced tables using
`ext_<extension>_<table>` (for example, `ext_example_signal`); they must not
add columns to SigmaRail tables. Missing core columns are planned for addition and
changed comments for update. Undeclared columns appear as blockers by default.
To explicitly delete them, run `sigmarail-schema --apply --drop-extra-columns`.
Column type changes are reported and require an explicit migration. Tables
outside the SigmaRail core contract are not inspected or modified.

## Core boundary

This repository also contains the SigmaRail Studio application. Its Django REST API,
React/Vite frontend, and consolidated Studio MCP live under `studio/`; the core Python
package and its SQL remain under `src/sigmarail/` and `sql/`. These are separate code
areas in one repository and share the same root test harness. The versioned
`sigmarail-spec` contract is maintained in `packages/sigmarail-spec/` as an
independently versioned Python distribution. The custom LEAN engine remains a separate repository.

The schema includes the 13 Sharadar source tables and the complete SQL
dependency closure for these primary screener outputs:

- `screener_price_tech_daily`
- `screener_fundamentals_daily`
- `screener_ratings_daily`
- `screener_stage_weekly_daily`
- `screener_ownership_daily`

The schema also includes Sharadar-only SQL transforms for asset returns,
factor residuals and screener factors, forecasts, forward returns, VCP pivots,
group strength, SATA score, RVAB, market context, canonical regime signals,
and per-symbol technical features. `daily_prices` is included as a normalized
OHLCV surface. Each included derived table resolves through its SQL inputs to
Sharadar source tables.
The field-level inventory and source closure are in
[`spec/lineage-manifest.json`](spec/lineage-manifest.json); scope decisions are
recorded in [`docs/LINEAGE_SCOPE.md`](docs/LINEAGE_SCOPE.md).
The current inventory contains 70 tables and 1,844 columns, including all 13
Sharadar source-table schemas.

KB sentiment, analyst estimates, external classification overlays, portfolio
allocations, and policy-composed regime/backtest views remain outside the
schema. The excluded fields and tables are enumerated in the lineage spec. The
external-overlay `gic_*` fields are omitted from `ticker_classification_daily`.

The core module also exposes a bounded, read-only query API for schema-declared tables.
Its dataset and join catalog is generated from the packaged lineage manifest plus reviewed
grain annotations; it does not modify core tables or load optional provider data. See
[`docs/QUERY_API.md`](docs/QUERY_API.md) for the query contract and supported joins.

## Initial setup

1. Install ClickHouse and create the database with `sql/init.sql`.
2. Copy `config.yaml.example` to SigmaRail's user config directory, then enter your
   ClickHouse and Sharadar credentials locally. The default directory is
   `~/.config/sigmarail` on Linux, `~/Library/Application Support/sigmarail` on macOS,
   and `%APPDATA%\sigmarail` on Windows. For an isolated test database, copy
   `config-test.yaml.example` to `config-test.yaml` in the same directory.
3. Install Core, Spec, and Studio together from the repository root:
   `python -m pip install -e 'packages/sigmarail-spec[build,test]' -e ".[dev]" -e "./studio[dev]"`.
4. Review the schema plan with `sigmarail-schema`, then apply it with
   `sigmarail-schema --apply`.
5. Install Studio-owned application tables with `sigmarail-studio-schema`.
6. Download and load Sharadar sources with `sigmarail-load --download`.
7. Build the derived screening tables with `sigmarail-populate --metrics all`.

Installed settings use the OS-specific user config directory above. Existing
project-local `config.yaml` files are still honored, and `SIGMARAIL_HOME` can point
to a custom config/data directory (for example, `~/.sigmarail`). Downloaded data and
logs remain relative to the current directory or `SIGMARAIL_HOME`. Use `--mode test`
for the isolated `sigmarail_test` database. The test configuration is rejected if it
points at the configured production database.

## Scope of the commands

`sigmarail-load` accepts only the Sharadar tables defined in the packaged source
schema. `sigmarail-populate` discovers transforms only from the packaged core
manifest and rejects targets outside that set. Schema SQL remains the source
of truth; `sigmarail-schema` defaults to a read-only plan. Use `sigmarail-schema --apply`
to stage statements as table creation, reconciliation, view removal, and view
creation so dependent views are refreshed safely. Deleting undeclared columns
requires both `--apply` and `--drop-extra-columns`.

## Tests

The suite covers the Sharadar loader, transform parser and schedule, schema
lineage, SQL calculation checks, and end-to-end transforms. ClickHouse tests
generate deterministic, synthetic source rows in a temporary directory. The
generated values are shaped to exercise the source schema and transforms; they
are not Sharadar observations and do not claim to represent market statistics.
No provider test files are needed in the checkout or CI.

Database-free checks run with `python -m pytest`. This single suite collects both
Core tests under `tests/` and Django API tests under `studio/tests/`. To run the
complete suite against the shared disposable ClickHouse container, use:

```bash
python -m pytest --sigmarail-clickhouse
```

The root pytest fixtures use Docker Compose to start the pinned ClickHouse image
once for the whole Core-and-Studio test session, wait for its health check, create
`sigmarail_test`, load synthetic source rows, and populate the shared baseline.
Core and Studio integration tests use that same database and may add test data
during the run. Pytest then captures the
container log under `logs/` and removes the test service. The database uses
ephemeral storage and is discarded at the end of the run; generated CSVs live
in a temporary directory and are deleted after the session. The first run
downloads the ClickHouse image. Docker and the Docker Compose plugin must
already be installed and running; SigmaRail does not install or start Docker itself.

GitHub Actions runs the same `python -m pytest --sigmarail-clickhouse` command on a
GitHub-hosted Linux runner. It generates the same temporary synthetic profile,
so private Sharadar fixture files and local database state are not uploaded. After
that suite passes, a separate self-hosted Apple Silicon job generates the same
deterministic synthetic profile in its own disposable ClickHouse container and
runs the full SigmaRail API-to-LEAN smoke against the private platform engine
image. For private strategy/image access, configure the
`SIGMARAIL_PLATFORM_READ_TOKEN` repository secret with read access to the strategy
repository and the GHCR package, or grant the SigmaRail repository access to both.
Fork pull requests do not run on the self-hosted runner.

If you already have an isolated, populated `sigmarail_test` database, the legacy
manual path remains available with `SIGMARAIL_RUN_POPULATE_TESTS=1`. Schema-only
checks against an existing test server can be enabled with
`SIGMARAIL_RUN_CLICKHOUSE_TESTS=1`. Both paths enforce the `sigmarail_test` database name.
The VCP pivot transform remains on hold and its empty state is asserted
explicitly.

The PyPI release and open-source license selection remain pending.
