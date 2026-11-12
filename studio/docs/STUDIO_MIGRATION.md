# SigmaRail Studio migration map

Studio is a set of paths inside the SigmaRail repository, not a separate repository.
Root `conftest.py` owns the single Compose service, synthetic data generation, Core
schema setup, and shared populated `sigmarail_test` database. Studio-owned application
tables live under `studio/screens/sql/schema/` and are applied by
`sigmarail-studio-schema`; they stay outside Core's generated financial data contract.
Running pytest from the repository root collects `tests/` and `studio/tests/`; Studio
integration tests reuse the `global_client` fixture rather than starting another
ClickHouse instance.

## Goal

Move the existing Studio application into the SigmaRail project family while retaining useful research and authoring behavior. Replace dependencies at their ownership boundaries; do not rename external contracts or pretend an unported runtime already exists.

## Migration classification

| Area | Current source state | SigmaRail destination | Treatment |
|---|---|---|---|
| Django API shell, React/Vite application, charts, shared UI state | Studio-owned code | `studio/` in SigmaRail | Moved as the application baseline; continue renaming UI and package identity here |
| Consolidated MCP server and domain organization | `sigmarail_studio_mcp/` after package rename | `studio/sigmarail_studio_mcp/` | Keep one server, split by functional domain, and expose the versioned SigmaRail Spec as Resources |
| Sharadar schema, transforms, and derived metrics | Existing SQL/query integration | SigmaRail core | Use SigmaRail SQL and generated spec as contract truth; do not copy SQL into Studio |
| Field catalogs, schema/lineage discovery | Vera query modules today | SigmaRail Spec + Studio query adapter | First backend slice: serve spec resources and implement schema-bound, read-only queries against declared SigmaRail tables/fields |
| Screener execution and saved queries | Existing `screen_stocks`, universe-query compiler, presets, and persistence | SigmaRail core/query service + Spec + Studio | Adapt query AST and supported fields to current SigmaRail schema; keep compatibility only while the replacement is incomplete |
| Expression AST and evaluator | Shared expression contract | SigmaRail Spec | Consume the published package; expose its supported forms in Studio, without copying a second evaluator |
| Five-slot strategy authoring | Existing Studio models and renderer | SigmaRail Spec + Studio | Preserve current authoring behavior where supported; version any wire-format change separately |
| Backtest, optimization, portfolio, LEAN runtime, deployment | Existing Vera Trading Lab and database integrations | SigmaRail Lean + Studio | Preserve interface concepts; migrate only when the SigmaRail runtime APIs and execution contracts exist |
| Knowledge base and external-source research | KnowledgeBase and non-core providers | Optional Studio integrations | Keep separate from the SigmaRail core data product and expose only as explicitly enabled modules |
| Local database purge/maintenance scripts | Includes source-specific destructive operations | None by default | Exclude from migration unless each operation is redesigned with explicit target selection and safety checks |

## Verified source-to-target gaps

- The source Studio imports `vera_query_core` across 27 Python files for screen execution, field/column registries, query compilation, templates, ClickHouse configuration, strategy validation, and runtime reports.
- SigmaRail Core owns SQL schema, transforms, loading/population, configuration, and low-level ClickHouse access. The query/screener runtime is being added alongside Studio in this repository.
- SigmaRail Spec publishes machine-readable data/field/lineage documents and expression/strategy contracts. It describes capabilities; it does not execute ClickHouse queries or run strategies.
- The current strategy payload includes a `VeraBase` section and the versioned `VeraLabV1` executable shape. Keep these wire keys accepted during the first migration. Rename or replace them only through a separately versioned compatibility change.
- Knowledge-base tools depend on external-source acquisition and must remain an optional integration. They are outside the SigmaRail core data contract.
- The source database environment utility includes destructive operations against the old production database. It is not carried as a Studio migration target.

## Current implementation increment

- The `core` MCP module is registered by default and calls SigmaRail's `list_datasets`,
  `describe_dataset`, and bounded `query_dataset` service. Its query fields, joins, and
  lineage come from the SigmaRail SQL-generated module manifest.
- Studio MCP Resources load from the installed `sigmarail-spec` package.
- The default MCP module set is `core,studio`. Vera-backed screening, strategy, backtest,
  portfolio, deployment, and knowledge tool groups require explicit selection through
  `SIGMARAIL_STUDIO_MODULES`. The server refuses to start those groups without local
  `vera_query_core`.
- This is an activation boundary, not completion of those migrations. Their implementations
  remain in compatibility adapters, and the web application's corresponding endpoints are
  still being migrated separately.

## Recommended implementation order

1. Complete application identity, packaging, and documentation renames in this repository while preserving saved-screen and strategy compatibility.
2. Add the canonical SigmaRail Spec dependency and MCP Resources for its compact index and focused data/field/transform/expression/strategy slices.
3. Add a SigmaRail read-only query adapter. Validate table, field, grain, sort, and filter references against Spec; generate bounded parameterized queries; use separate read-only credentials and make no schema changes from Studio.
4. Port saved universe-query validation/compilation and screener execution to that adapter. Reconcile current screener/table names with the SigmaRail catalog instead of retaining legacy `screener_*` assumptions.
5. Reconnect the Studio authoring UI to the SigmaRail Spec expression and five-slot schemas, and preserve the previous format through explicit compatibility adapters.
6. Migrate LEAN/backtest/deploy features only after SigmaRail Lean exposes the corresponding runtime contracts. Keep current backend integrations isolated behind adapters until then.
7. Move KB and other provider integrations into optional modules with independent settings and availability reporting.
8. Recreate the Turnip HTTPS/Tailscale and MCP hosting route for SigmaRail Studio after the new MCP endpoint is ready. Keep the existing Vera route running during cutover; switch only after read/write parity checks and explicit acceptance.

## Hosting boundary

The local Turnip setup currently uses Tailscale Serve/Funnel in front of local HTTP services and a Supergateway route that serves the existing MCP. This repository should own its MCP transport configuration and health endpoint, but local host services and route changes belong to a separate deployment step. Never alter or stop an existing service as part of local code migration.

## Release readiness gaps

Before publishing this repository as an open-source installable application, resolve the remaining private/source-runtime dependencies, set the project license, define installation and configuration for a clean machine, and provide tests using synthetic or otherwise distributable data. Core and Studio now share one pytest/ClickHouse lifecycle; the current snapshot is local migration work, not a published release.
