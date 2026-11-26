# SigmaRail Studio services

The SigmaRail research and strategy-authoring UI runs in AppTension. This directory
contains the Django API, MCP host, and supporting services still being migrated.

The AppTension web application owns the SigmaRail UI in
`packages/webapp/src/sigmaRail/`. The Django REST API and consolidated MCP remain
under `studio/` while their service migration is evaluated. The feature migration is ongoing; see
[the migration map](docs/STUDIO_MIGRATION.md) for what is implemented and what
remains to be adapted.

## Three-project architecture

- **SigmaRail Spec** owns the product description, architecture, and versioned data, query, expression,
  authoring, strategy, and slot contracts.
- **SigmaRail** owns this interface and its services, ClickHouse schema and transforms, data loading,
  query execution, API, and MCP integration.
- **SigmaRail Lean** owns the customized LEAN integration and strategy execution.

The interface and MCP are components of SigmaRail. They consume Spec contracts and call explicit
data/runtime services; they do not define a parallel strategy language, duplicate schema SQL, or
absorb the LEAN execution engine.

## Current migration status

The repository contains the Django API, the AppTension-hosted React application, and the domain-oriented MCP server. The standalone MCP currently exposes only SigmaRail Core data queries and SigmaRail Spec resources. Other copied Studio services are being reviewed individually; they must be migrated to SigmaRail-owned APIs or removed before release.

No production database or hosted service is configured by this repository. Local development here does not change any existing hosted service.

## MCP modules and local setup

The MCP provides `core` data tools and `studio` Spec resources. It does not load sibling
project source trees. Core query access requires the
SigmaRail database configuration. Additional domain modules will be exposed only after
their SigmaRail-owned implementations are available.

From the SigmaRail repository root, install the three local distributions in one command:

```bash
python -m pip install -e 'packages/sigmarail-spec[build,test]' -e ".[dev]" -e "./studio[dev]"
```

Run the combined Python suite from the repository root with
`python -m pytest --sigmarail-clickhouse`; Core and Studio use the same synthetic
ClickHouse service and `sigmarail_test` database. For the web application, run
`corepack pnpm install --frozen-lockfile`,
`corepack pnpm --filter webapp run type-check`, and
`corepack pnpm nx run webapp:build` from the repository root.

The Studio MCP launcher uses only the installed SigmaRail Core, Spec, and Studio paths.
