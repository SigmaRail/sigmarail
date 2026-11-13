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

The repository contains the Django API, React application, and domain-oriented MCP server. The standalone MCP currently exposes only SigmaRail Core data queries and SigmaRail Spec resources. Other copied Studio surfaces are being reviewed individually; they must be migrated to SigmaRail-owned APIs or removed before release.

No production database or hosted service is configured by this repository. Local development here does not change any existing hosted service.

## MCP modules and local setup

The MCP provides `core` data tools and `studio` Spec resources. It does not load sibling
project source trees. Core query access requires the
SigmaRail database configuration. Additional domain modules will be exposed only after
their SigmaRail-owned implementations are available.

From the SigmaRail repository root, install the separate Spec distribution and both
local packages in one command:

```bash
python -m pip install -e ../sigmarail-spec -e ".[dev]" -e "./studio[dev]"
```

Run the combined Python suite from the repository root with
`python -m pytest --sigmarail-clickhouse`; Core and Studio use the same synthetic
ClickHouse service and `sigmarail_test` database. For the frontend, run
`npm ci && npm test && npm run build` from `studio/frontend/`.

The Studio MCP launcher uses only the installed SigmaRail Core, Spec, and Studio paths.
