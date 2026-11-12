# SigmaRail Studio

SigmaRail Studio is the research and strategy-authoring application for the SigmaRail project family. It brings together market-data discovery, screener workflows, charts, strategy authoring, backtest review, and a consolidated MCP surface.

Studio is maintained in the SigmaRail repository under `studio/`. Its Django REST
API, React/Vite frontend, and consolidated MCP are separate paths within the same
codebase as SigmaRail Core. The feature migration is ongoing; see
[the migration map](docs/STUDIO_MIGRATION.md) for what is implemented and what
remains to be adapted.

## Intended project boundaries

- **SigmaRail Core** owns the financial data schema, transformations, loading, database population, and the root test database lifecycle.
- **SigmaRail Spec** owns the versioned data, expression, Studio-authoring, and strategy contracts.
- **SigmaRail Studio** owns the Django REST API, React/Vite interface, MCP host, query orchestration, and authoring workflow. It shares the SigmaRail repository and pytest suite with Core.
- **SigmaRail Lean** will own strategy execution and LEAN integration when that project is migrated.

Studio should consume the published contracts and call explicit data/runtime services. It should not duplicate schema SQL or absorb the LEAN execution engine.

## Current migration status

The repository currently contains the migrated Django API, React application, charting and authoring surfaces, and domain-oriented MCP server. Its screener, field catalog, strategy, backtest, deployment, portfolio, and knowledge-base adapters still include source-project integrations. These are being replaced by SigmaRail-owned interfaces in bounded steps; unsupported capabilities must not be advertised as available in the meantime.

No production database or hosted service is configured by this repository. Local development here does not change any existing hosted service.

## MCP modules and local setup

The MCP starts with `core` and `studio`. Core provides the SQL-derived dataset catalog,
field descriptions, and bounded read-only queries. Vera-derived screening, strategy,
backtesting, portfolio, deployment, and knowledge tools are optional compatibility modules
while their SigmaRail-owned replacements are migrated. Enable only the groups needed with
`SIGMARAIL_STUDIO_MODULES=core,studio,screening`; enabling a compatibility group requires the
local VeraBase package. Core query access requires the SigmaRail database configuration.

From the SigmaRail repository root, install the separate Spec distribution and both
local packages in one command:

```bash
python -m pip install -e ../sigmarail-spec -e ".[dev]" -e "./studio[dev]"
```

Run the combined Python suite from the repository root with
`python -m pytest --sigmarail-clickhouse`; Core and Studio use the same synthetic
ClickHouse service and `sigmarail_test` database. For the frontend, run
`npm ci && npm test && npm run build` from `studio/frontend/`.

The Studio default MCP modules are `core` and `studio`. Incomplete compatibility
modules stay opt-in until their SigmaRail implementations are ready. The local
launcher and optional adapters can still use the legacy VeraBase checkout where
those compatibility modules require it.
